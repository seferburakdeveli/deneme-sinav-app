from flask import Flask, render_template, request, redirect, url_for
import json, os, csv

app = Flask(__name__)

ANSWER_KEY_FILE = "answer_keys.json"
KATSAYILAR_FILE = "katsayilar.json"
STUDENT_CODES_FILE = "student_codes.csv"
STUDENT_ANSWERS_FILE = "student_answers.json"

# --- yardımcı yükleme fonksiyonları ---
def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_student_codes():
    # CSV: ogrenci_kodu <tab veya comma> ogrenci_adi (ilk satır başlık)
    if not os.path.exists(STUDENT_CODES_FILE):
        return {}
    with open(STUDENT_CODES_FILE, "r", encoding="utf-8") as f:
        sample = f.read().splitlines()
    if not sample:
        return {}
    # determine delimiter
    header = sample[0]
    delimiter = '\t' if '\t' in header else ','
    # use DictReader
    with open(STUDENT_CODES_FILE, newline='', encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile, delimiter=delimiter)
        mapping = {}
        for row in reader:
            kod = row.get("ogrenci_kodu") or row.get("ogrenciKod") or row.get("kod") or ""
            ad = row.get("ogrenci_adi") or row.get("ogrenci_adi") or row.get("isim") or ""
            kod = kod.strip()
            ad = ad.strip()
            if kod:
                mapping[kod] = ad
        return mapping

# 3 yanlış 1 doğru -> net = dogru - yanlis/3
def calc_nets_and_summary(ogrenci_cevaplari, cevap_anahtari, ders_sirasi):
    per_ders = {}
    for ders in ders_sirasi:
        if ders not in cevap_anahtari:
            continue
        anahtar = cevap_anahtari[ders]
        kullanici = ogrenci_cevaplari.get(ders, [])
        # ensure same length
        L = len(anahtar)
        # pad user answers with "" if missing
        if len(kullanici) < L:
            kullanici = kullanici + [""] * (L - len(kullanici))
        qstatus = []  # list of dict: {num, given, correct, durum}
        dogru = yanlis = bos = 0
        for i in range(L):
            g = (kullanici[i] or "").strip().upper()
            c = (anahtar[i] or "").strip().upper()
            if g == "":
                durum = "bos"
                bos += 1
            elif g == c:
                durum = "dogru"
                dogru += 1
            else:
                durum = "yanlis"
                yanlis += 1
            qstatus.append({"no": i+1, "given": g or "-", "correct": c, "durum": durum})
        net = dogru - (yanlis / 3.0)
        per_ders[ders] = {
            "dogru": dogru,
            "yanlis": yanlis,
            "bos": bos,
            "net": round(net, 2),
            "qstatus": qstatus
        }
    return per_ders

def calculate_total_score(per_ders, katsayilar):
    toplam = 0.0
    for ders, info in per_ders.items():
        katsayi = katsayilar.get(ders, 0)
        toplam += info["net"] * katsayi
    temel = katsayilar.get("temel_puan", 0)
    toplam += temel
    return round(toplam, 2)

# Sabit ders sırası (isteğe bağlı değiştirebilirsin)
DERS_SIRASI = [
    "Türkçe",
    "inkılap Tarihi",
    "Sosyal Bilgiler",
    "Din Kültürü ve Ahlak Bilgisi",
    "Yabancı Dil",
    "Matematik",
    "Fen Bilimleri"
]

# --- Routes ---
@app.route("/", methods=["GET", "POST"])
def index():
    cevap_anahtarlari = load_json(ANSWER_KEY_FILE)
    deneme_listesi = list(cevap_anahtarlari.keys())
    student_map = load_student_codes()
    katsayilar = load_json(KATSAYILAR_FILE)

    if request.method == "POST":
        ogrenci_kodu = request.form.get("ogrenci_kodu", "").strip()
        deneme_kodu = request.form.get("deneme_kodu", "").strip()

        # validasyon
        if not ogrenci_kodu:
            return render_template("index.html", hata="Öğrenci kodu girin.", deneme_listesi=deneme_listesi, cevap_anahtarlari=cevap_anahtarlari)
        if ogrenci_kodu not in student_map:
            return render_template("index.html", hata="Öğrenci kodu bulunamadı.", deneme_listesi=deneme_listesi, cevap_anahtarlari=cevap_anahtarlari)
        if not deneme_kodu or deneme_kodu not in cevap_anahtarlari:
            return render_template("index.html", hata="Geçersiz deneme seçimi.", deneme_listesi=deneme_listesi, cevap_anahtarlari=cevap_anahtarlari)

        # Kullanıcının cevaplarını oku (form alan isimleri: "{ders}_{soruNo}")
        deneme_anahtari = cevap_anahtarlari[deneme_kodu]
        ogrenci_cevaplari = {}
        for ders in DERS_SIRASI:
            if ders in deneme_anahtari:
                L = len(deneme_anahtari[ders])
                arr = []
                for i in range(L):
                    key = f"{ders}_{i+1}"
                    val = request.form.get(key, "").strip().upper()
                    arr.append(val)
                ogrenci_cevaplari[ders] = arr

        # kaydet
        all_answers = load_json(STUDENT_ANSWERS_FILE)
        if deneme_kodu not in all_answers:
            all_answers[deneme_kodu] = {}
        all_answers[deneme_kodu][ogrenci_kodu] = ogrenci_cevaplari
        save_json(STUDENT_ANSWERS_FILE, all_answers)

        # hesaplama
        per_ders = calc_nets_and_summary(ogrenci_cevaplari, deneme_anahtari, DERS_SIRASI)
        toplam_puan = calculate_total_score(per_ders, katsayilar)

        # sıralama (tüm öğrenciler o deneme için)
        ranking = []
        for kod, cevaplar in all_answers.get(deneme_kodu, {}).items():
            per = calc_nets_and_summary(cevaplar, deneme_anahtari, DERS_SIRASI)
            puan = calculate_total_score(per, katsayilar)
            ranking.append({"ogrenci_kodu": kod, "ogrenci_adi": student_map.get(kod, ""), "puan": puan})
        ranking.sort(key=lambda x: x["puan"], reverse=True)

        return render_template(
            "result.html",
            ogrenci_kodu=ogrenci_kodu,
            ogrenci_adi=student_map.get(ogrenci_kodu, ""),
            deneme_kodu=deneme_kodu,
            per_ders=per_ders,
            toplam_puan=toplam_puan,
            ranking=ranking,
            katsayilar=katsayilar,
            cevap_anahtari=deneme_anahtari,
            ders_sirasi=DERS_SIRASI
        )

    # GET
    return render_template("index.html", deneme_listesi=deneme_listesi, cevap_anahtarlari=load_json(ANSWER_KEY_FILE))

# run
if __name__ == "__main__":
    app.run(debug=True)
