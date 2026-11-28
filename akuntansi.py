"""
akuntansi.py
============
Semua logika akuntansi ada di file ini dan dihitung oleh PYTHON, bukan oleh AI.

Alur siklus akuntansi:
    Transaksi -> Jurnal Umum -> Buku Besar -> Neraca Saldo -> Laporan Keuangan

Catatan desain (v3):
    - Daftar akun (COA) kini DINAMIS per pengguna. Semua fungsi menerima parameter
      `coa` (dict {nama: (kategori, saldo_normal)}); jika None dipakai daftar bawaan `AKUN`.
      Tidak ada variabel global yang diubah, jadi aman dipakai banyak pengguna sekaligus.
    - Daftar akun disimpan sebagai list of dict: {"kode","nama","kategori","normal"}.
"""

import io
import json
import re
from datetime import datetime

import pandas as pd

# ---------------------------------------------------------------------------
# 1. DAFTAR AKUN BAWAAN (Chart of Accounts)
#    Format:  "Nama Akun": ("Kategori", "Saldo Normal")
# ---------------------------------------------------------------------------
AKUN = {
    # ASET
    "Kas": ("Aset", "debit"),
    "Piutang Usaha": ("Aset", "debit"),
    "Persediaan": ("Aset", "debit"),
    "Perlengkapan": ("Aset", "debit"),
    "Peralatan": ("Aset", "debit"),
    # LIABILITAS
    "Utang Usaha": ("Liabilitas", "kredit"),
    "Utang Bank": ("Liabilitas", "kredit"),
    # EKUITAS
    "Modal Pemilik": ("Ekuitas", "kredit"),
    "Prive": ("Ekuitas", "debit"),
    # PENDAPATAN
    "Penjualan": ("Pendapatan", "kredit"),
    "Pendapatan Jasa": ("Pendapatan", "kredit"),
    # BEBAN
    "Beban Pokok Penjualan": ("Beban", "debit"),
    "Beban Gaji": ("Beban", "debit"),
    "Beban Sewa": ("Beban", "debit"),
    "Beban Listrik dan Air": ("Beban", "debit"),
    "Beban Perlengkapan": ("Beban", "debit"),
    "Beban Lain-lain": ("Beban", "debit"),
}

URUTAN_KATEGORI = ["Aset", "Liabilitas", "Ekuitas", "Pendapatan", "Beban"]

# Sisi "alami" tiap kategori. Akun dengan saldo normal berlawanan dianggap akun
# pengurang (mis. Prive di Ekuitas, Akumulasi Penyusutan di Aset).
NORMAL_KATEGORI = {
    "Aset": "debit",
    "Liabilitas": "kredit",
    "Ekuitas": "kredit",
    "Pendapatan": "kredit",
    "Beban": "debit",
}

PREFIX_KODE = {"Aset": 1, "Liabilitas": 2, "Ekuitas": 3, "Pendapatan": 4, "Beban": 5}

# Akun yang dirujuk oleh aturan prompt AI dan laporan: nama, kategori, dan saldo
# normalnya dikunci (hanya kodenya yang boleh diubah) dan tidak boleh dihapus.
AKUN_INTI = {
    "Kas", "Piutang Usaha", "Persediaan", "Utang Usaha",
    "Modal Pemilik", "Prive", "Penjualan", "Beban Pokok Penjualan",
}

VERSI_SNAPSHOT = 2


def _coa(coa):
    """None -> daftar bawaan."""
    return AKUN if coa is None else coa


# Nama kategori di penyimpanan tetap "Liabilitas"/"Ekuitas" (kompatibel dengan snapshot lama),
# tetapi pengguna boleh menulis/memilih "Kewajiban", "Modal", dll. Label tampilan ada di LABEL_KATEGORI.
ALIAS_KATEGORI = {
    "aset": "Aset", "aktiva": "Aset",
    "liabilitas": "Liabilitas", "kewajiban": "Liabilitas", "utang": "Liabilitas", "hutang": "Liabilitas",
    "ekuitas": "Ekuitas", "modal": "Ekuitas", "ekuitas / modal": "Ekuitas", "ekuitas/modal": "Ekuitas",
    "pendapatan": "Pendapatan", "penghasilan": "Pendapatan",
    "beban": "Beban", "biaya": "Beban",
}

LABEL_KATEGORI = {
    "Aset": "Aset",
    "Liabilitas": "Kewajiban",
    "Ekuitas": "Ekuitas / Modal",
    "Pendapatan": "Pendapatan",
    "Beban": "Beban",
}


def normalisasi_kategori(kategori):
    """'kewajiban' / 'Modal' / ' ASET ' -> nama kategori baku; selain itu dikembalikan apa adanya."""
    mentah = " ".join(str(kategori or "").split())
    return ALIAS_KATEGORI.get(mentah.lower(), mentah)


def label_kategori(kategori):
    """Nama kategori baku -> label tampilan (mis. Liabilitas -> Kewajiban)."""
    return LABEL_KATEGORI.get(kategori, str(kategori))


def _kunci_nama(nama):
    """Pembanding nama akun: abaikan huruf besar/kecil dan spasi berlebih."""
    return " ".join(str(nama or "").split()).lower()


def _kunci_kode(kode):
    """Pembanding kode akun: abaikan huruf besar/kecil dan spasi."""
    return "".join(str(kode or "").split()).lower()


# ---------------------------------------------------------------------------
# 2. KELOLA DAFTAR AKUN (COA)
# ---------------------------------------------------------------------------
def coa_default():
    """Daftar akun bawaan sebagai list of dict lengkap dengan kode akun (101, 102, ...)."""
    hitung = {k: 0 for k in URUTAN_KATEGORI}
    daftar = []
    for nama, (kat, normal) in AKUN.items():
        hitung[kat] += 1
        daftar.append({
            "kode": f"{PREFIX_KODE[kat]}{hitung[kat]:02d}",
            "nama": nama,
            "kategori": kat,
            "normal": normal,
        })
    return daftar


def urutkan_coa(daftar):
    """Urutkan list akun berdasarkan kategori, lalu kode, lalu nama."""
    return sorted(
        daftar,
        key=lambda a: (URUTAN_KATEGORI.index(a["kategori"]), str(a["kode"]), a["nama"]),
    )


def coa_ke_peta(daftar):
    """list of dict -> dict {nama: (kategori, normal)} (terurut)."""
    return {a["nama"]: (a["kategori"], a["normal"]) for a in urutkan_coa(daftar)}


def daftar_akun_df(daftar=None):
    """Tabel daftar akun untuk ditampilkan."""
    daftar = coa_default() if daftar is None else daftar
    return pd.DataFrame(
        [
            {"Kode": a["kode"], "Akun": a["nama"], "Kategori": a["kategori"],
             "Saldo Normal": a["normal"].capitalize()}
            for a in urutkan_coa(daftar)
        ],
        columns=["Kode", "Akun", "Kategori", "Saldo Normal"],
    )


def kode_berikutnya(daftar, kategori):
    """Saran kode akun berikutnya yang belum dipakai untuk suatu kategori."""
    dipakai = {_kunci_kode(a["kode"]) for a in daftar}
    kategori = normalisasi_kategori(kategori)
    prefix = PREFIX_KODE.get(kategori, 9)
    for n in range(1, 1000):
        kode = f"{prefix}{n:02d}"
        if kode.lower() not in dipakai:
            return kode
    return f"{prefix}999"


def periksa_akun(daftar, kode, nama, kategori, normal, abaikan=None):
    """
    Validasi satu akun terhadap daftar yang ada.
    Duplikat nama/kode dideteksi tanpa membedakan huruf besar/kecil dan spasi berlebih.
    `abaikan` = nama akun yang sedang diedit (tidak dihitung sebagai duplikat).
    Return: (daftar_error, kode_bersih, nama_bersih)
    """
    errors = []
    kode = "".join(str(kode or "").split())
    nama = " ".join(str(nama or "").split())
    kategori = normalisasi_kategori(kategori)
    normal = str(normal or "").strip().lower()

    if not re.fullmatch(r"[A-Za-z0-9.\-]{1,10}", kode):
        errors.append("Kode akun harus 1–10 karakter: huruf, angka, titik, atau strip.")
    if not 2 <= len(nama) <= 40:
        errors.append("Nama akun harus 2–40 karakter.")
    elif not re.fullmatch(r"[\w .,&()/\-]+", nama):
        errors.append("Nama akun hanya boleh berisi huruf, angka, spasi, dan tanda . , & ( ) / -")
    if kategori not in URUTAN_KATEGORI:
        errors.append("Kategori tidak valid.")
    if normal not in ("debit", "kredit"):
        errors.append("Saldo normal harus 'debit' atau 'kredit'.")

    for a in daftar:
        if abaikan is not None and a["nama"] == abaikan:
            continue
        if nama and _kunci_nama(a["nama"]) == _kunci_nama(nama):
            errors.append(f"Nama akun '{nama}' sudah dipakai akun '{a['nama']}'.")
        if kode and _kunci_kode(a["kode"]) == _kunci_kode(kode):
            errors.append(f"Kode '{kode}' sudah dipakai akun '{a['nama']}'.")
    return errors, kode, nama


def jumlah_pemakaian(jurnal):
    """dict {akun: jumlah transaksi yang memakai akun tersebut}."""
    hasil = {}
    for t in jurnal:
        for akun in {b["akun"] for b in t["baris"]}:
            hasil[akun] = hasil.get(akun, 0) + 1
    return hasil


def ganti_nama_akun(jurnal, lama, baru):
    """Ganti nama akun di seluruh jurnal (dipakai saat akun diubah namanya)."""
    for t in jurnal:
        for b in t["baris"]:
            if b["akun"] == lama:
                b["akun"] = baru


def coa_tambah(daftar, kode, nama, kategori, normal):
    """
    Tambah akun ke `daftar` (diubah di tempat). Kode yang dikosongkan diisi otomatis
    sesuai kategori. Return list error (kosong = berhasil); akun baru ada di daftar[-1].
    """
    kategori = normalisasi_kategori(kategori)
    if not "".join(str(kode or "").split()) and kategori in URUTAN_KATEGORI:
        kode = kode_berikutnya(daftar, kategori)
    errors, kode, nama = periksa_akun(daftar, kode, nama, kategori, normal)
    if errors:
        return errors
    daftar.append({"kode": kode, "nama": nama, "kategori": kategori, "normal": str(normal).strip().lower()})
    return []


def coa_ubah(daftar, nama_lama, kode, nama, kategori, normal, jurnal):
    """
    Ubah satu akun. Akun inti hanya boleh diubah kodenya.
    Jika nama berubah, seluruh jurnal ikut diperbarui. Return list error.
    """
    idx = next((i for i, a in enumerate(daftar) if a["nama"] == nama_lama), None)
    if idx is None:
        return ["Akun tidak ditemukan."]
    kategori = normalisasi_kategori(kategori)
    if nama_lama in AKUN_INTI:
        nama, kategori, normal = nama_lama, daftar[idx]["kategori"], daftar[idx]["normal"]
    errors, kode, nama = periksa_akun(daftar, kode, nama, kategori, normal, abaikan=nama_lama)
    if errors:
        return errors
    daftar[idx] = {"kode": kode, "nama": nama, "kategori": kategori, "normal": str(normal).strip().lower()}
    if nama != nama_lama:
        ganti_nama_akun(jurnal, nama_lama, nama)
    return []


def coa_hapus(daftar, nama, jurnal):
    """Hapus akun jika bukan akun inti dan belum dipakai di jurnal. Return list error."""
    if nama in AKUN_INTI:
        return [f"'{nama}' adalah akun inti dan tidak bisa dihapus."]
    n = jumlah_pemakaian(jurnal).get(nama, 0)
    if n:
        return [f"'{nama}' dipakai di {n} transaksi. Ubah atau hapus transaksinya dulu."]
    daftar[:] = [a for a in daftar if a["nama"] != nama]
    return []


def coa_kembalikan(daftar, jurnal):
    """Kembalikan daftar akun ke bawaan, jika semua akun di jurnal ada di daftar bawaan."""
    asing = sorted(set(jumlah_pemakaian(jurnal)) - set(AKUN))
    if asing:
        return ["Akun berikut dipakai di jurnal tetapi tidak ada di daftar bawaan: " + ", ".join(asing)]
    daftar[:] = coa_default()
    return []


# ---------------------------------------------------------------------------
# 3. FORMAT UANG
# ---------------------------------------------------------------------------
def ke_angka(nilai):
    """
    Mengubah berbagai penulisan uang menjadi angka bulat rupiah.
    Contoh: 500000 -> 500000 | "500rb" -> 500000 | "Rp 1,5 juta" -> 1500000
            "2jt" -> 2000000 | "1.500.000" -> 1500000
    """
    if isinstance(nilai, bool):
        raise ValueError("Nominal tidak valid")
    if isinstance(nilai, (int, float)):
        return int(round(nilai))

    teks = str(nilai).lower().replace("rp", "").replace(" ", "").strip()
    cocok = re.fullmatch(r"([\d.,]+)(juta|jt|ribu|rb|k|miliar|milyar)?", teks)
    if not cocok:
        raise ValueError(f"Nominal tidak dapat dibaca: {nilai!r}")

    angka, satuan = cocok.group(1), cocok.group(2)
    pengali = {
        None: 1, "k": 1_000, "rb": 1_000, "ribu": 1_000,
        "jt": 1_000_000, "juta": 1_000_000,
        "miliar": 1_000_000_000, "milyar": 1_000_000_000,
    }[satuan]

    if satuan:
        angka = angka.replace(",", ".")
        if angka.count(".") > 1:
            angka = angka.replace(".", "")
        return int(round(float(angka) * pengali))

    return int(angka.replace(".", "").replace(",", ""))


def rp(nilai):
    """Format angka menjadi 'Rp10.700.000'."""
    return "Rp" + f"{int(round(nilai)):,}".replace(",", ".")


def fmt_angka(v):
    """Format angka dengan titik ribuan (untuk tabel). Nol ditampilkan '0'."""
    if pd.isna(v):
        return ""
    return f"{int(round(v)):,}".replace(",", ".")


def fmt_kosong(v):
    """Sama seperti fmt_angka, tetapi nol dikosongkan (untuk kolom debit/kredit)."""
    if pd.isna(v) or int(round(v)) == 0:
        return ""
    return fmt_angka(v)


# ---------------------------------------------------------------------------
# 4. VALIDASI TRANSAKSI  (INI TUGAS PYTHON, BUKAN AI)
# ---------------------------------------------------------------------------
def periksa_transaksi(transaksi, coa=None):
    """
    Membersihkan dan memvalidasi satu transaksi.
    Return: (transaksi_bersih, daftar_error). Jika daftar_error kosong -> valid.
    """
    coa = _coa(coa)
    peta_nama = {nama.lower(): nama for nama in coa}
    errors = []
    bersih = {
        "tanggal": transaksi.get("tanggal"),
        "keterangan": str(transaksi.get("keterangan") or "").strip(),
        "baris": [],
    }

    if not bersih["keterangan"]:
        errors.append("Keterangan transaksi kosong.")

    baris_mentah = transaksi.get("baris") or []
    if len(baris_mentah) < 2:
        errors.append("Jurnal minimal memiliki 2 baris (satu debit dan satu kredit).")

    total_debit = total_kredit = 0
    for i, b in enumerate(baris_mentah, start=1):
        nama = str(b.get("akun") or "").strip()
        nama_resmi = peta_nama.get(nama.lower())
        if not nama_resmi:
            errors.append(f"Baris {i}: akun '{nama}' tidak ada di daftar akun.")
            continue

        posisi = str(b.get("posisi") or "").strip().lower()
        if posisi not in ("debit", "kredit"):
            errors.append(f"Baris {i}: posisi '{posisi}' harus 'debit' atau 'kredit'.")
            continue

        try:
            nominal = ke_angka(b.get("nominal"))
        except (ValueError, TypeError):
            errors.append(f"Baris {i}: nominal '{b.get('nominal')}' tidak valid.")
            continue
        if nominal <= 0:
            errors.append(f"Baris {i}: nominal harus lebih dari 0.")
            continue

        bersih["baris"].append({"akun": nama_resmi, "posisi": posisi, "nominal": nominal})
        if posisi == "debit":
            total_debit += nominal
        else:
            total_kredit += nominal

    if bersih["baris"] and not errors:
        if total_debit == 0 or total_kredit == 0:
            errors.append("Jurnal harus memiliki sisi debit DAN sisi kredit.")
        elif total_debit != total_kredit:
            errors.append(
                f"Total debit ({rp(total_debit)}) tidak sama dengan total kredit "
                f"({rp(total_kredit)}); selisih {rp(abs(total_debit - total_kredit))}."
            )

    return bersih, errors


def parse_json_ai(teks):
    """Mengambil objek JSON dari jawaban AI (membuang ```json ... ``` jika ada)."""
    if not teks:
        raise ValueError("Jawaban AI kosong.")
    teks = re.sub(r"```(?:json)?", "", teks).strip()
    awal, akhir = teks.find("{"), teks.rfind("}")
    if awal == -1 or akhir == -1 or akhir < awal:
        raise ValueError("Jawaban AI bukan JSON.")
    try:
        return json.loads(teks[awal : akhir + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON dari AI rusak: {e}")


# ---------------------------------------------------------------------------
# 5. JURNAL UMUM
#    jurnal = list transaksi yang sudah disetujui pengguna:
#    {"no": 1, "tanggal": "2026-11-26", "keterangan": "...", "baris": [...]}
# ---------------------------------------------------------------------------
def jurnal_ke_df(jurnal):
    """Jurnal -> DataFrame 'datar' (satu baris per akun) untuk dihitung."""
    data = []
    for t in jurnal:
        for b in t["baris"]:
            data.append({
                "No": t["no"],
                "Tanggal": t["tanggal"],
                "Keterangan": t["keterangan"],
                "Akun": b["akun"],
                "Debit": b["nominal"] if b["posisi"] == "debit" else 0,
                "Kredit": b["nominal"] if b["posisi"] == "kredit" else 0,
            })
    return pd.DataFrame(data, columns=["No", "Tanggal", "Keterangan", "Akun", "Debit", "Kredit"])


def jurnal_tampil_df(jurnal):
    """
    Versi tampilan jurnal umum: akun kredit dijorok ke kanan, seperti
    penulisan jurnal di buku akuntansi. Keterangan hanya di baris pertama.
    """
    df = jurnal_ke_df(jurnal).copy()
    if df.empty:
        return df
    jorok = "\u00a0" * 6
    df["Akun"] = [a if k == 0 else jorok + a for a, k in zip(df["Akun"], df["Kredit"])]
    pertama = ~df["No"].duplicated()
    for kolom in ["No", "Tanggal", "Keterangan"]:
        df[kolom] = df[kolom].astype(str)
        df.loc[~pertama, kolom] = ""
    return df


def nomori_ulang(jurnal):
    """Beri nomor ulang 1..n (dipanggil setelah ada transaksi yang dihapus)."""
    for i, t in enumerate(jurnal, start=1):
        t["no"] = i
    return jurnal


def filter_jurnal(jurnal, awal=None, akhir=None, akun=None, kata=""):
    """
    Menyaring transaksi berdasarkan rentang tanggal, akun, dan kata kunci keterangan.
    Transaksi diambil UTUH (bukan per baris) agar debit = kredit tetap terjaga.
    awal/akhir boleh berupa date atau string 'YYYY-MM-DD'.
    """
    kata = (kata or "").strip().lower()
    akun = set(akun or [])
    hasil = []
    for t in jurnal:
        tgl = str(t.get("tanggal") or "")
        if awal and tgl < str(awal):
            continue
        if akhir and tgl > str(akhir):
            continue
        if akun and not akun & {b["akun"] for b in t["baris"]}:
            continue
        if kata and kata not in t["keterangan"].lower():
            continue
        hasil.append(t)
    return hasil


# ---------------------------------------------------------------------------
# 6. BUKU BESAR
# ---------------------------------------------------------------------------
def akun_terpakai(jurnal, coa=None):
    """Akun yang muncul di jurnal, diurutkan sesuai daftar akun."""
    coa = _coa(coa)
    df = jurnal_ke_df(jurnal)
    dipakai = set(df["Akun"]) if not df.empty else set()
    return [a for a in coa if a in dipakai]


def buku_besar(jurnal, akun, coa=None):
    """
    Mutasi satu akun beserta saldo berjalan (mengikuti saldo normal akun).
    Return: (DataFrame, saldo_akhir)
    """
    coa = _coa(coa)
    df = jurnal_ke_df(jurnal)
    df = df[df["Akun"] == akun].copy()
    normal = coa[akun][1]
    if normal == "debit":
        df["Saldo"] = (df["Debit"] - df["Kredit"]).cumsum()
    else:
        df["Saldo"] = (df["Kredit"] - df["Debit"]).cumsum()
    df = df[["Tanggal", "No", "Keterangan", "Debit", "Kredit", "Saldo"]].rename(
        columns={"No": "No. Jurnal"}
    )
    saldo_akhir = int(df["Saldo"].iloc[-1]) if not df.empty else 0
    return df.reset_index(drop=True), saldo_akhir


def saldo_semua_akun(jurnal, coa=None):
    """Dictionary {akun: saldo} (positif = di sisi saldo normal)."""
    hasil = {}
    for akun in akun_terpakai(jurnal, coa):
        _, saldo = buku_besar(jurnal, akun, coa)
        hasil[akun] = saldo
    return hasil


# ---------------------------------------------------------------------------
# 7. NERACA SALDO
# ---------------------------------------------------------------------------
def neraca_saldo(jurnal, coa=None):
    """
    Neraca saldo: saldo akhir tiap akun diletakkan di kolom Debit atau Kredit.
    Return: (DataFrame, total_debit, total_kredit, seimbang)
    """
    df = jurnal_ke_df(jurnal)
    baris = []
    for akun in akun_terpakai(jurnal, coa):
        d = int(df.loc[df["Akun"] == akun, "Debit"].sum())
        k = int(df.loc[df["Akun"] == akun, "Kredit"].sum())
        bersih = d - k
        baris.append({
            "Akun": akun,
            "Debit": bersih if bersih > 0 else 0,
            "Kredit": -bersih if bersih < 0 else 0,
        })
    hasil = pd.DataFrame(baris, columns=["Akun", "Debit", "Kredit"])
    total_d = int(hasil["Debit"].sum()) if not hasil.empty else 0
    total_k = int(hasil["Kredit"].sum()) if not hasil.empty else 0
    return hasil, total_d, total_k, total_d == total_k


# ---------------------------------------------------------------------------
# 8. LAPORAN KEUANGAN (laba rugi + posisi keuangan)
#    Nilai tiap akun diberi tanda terhadap sisi alami kategorinya, sehingga akun
#    pengurang (mis. Prive) otomatis bernilai negatif di kategorinya.
# ---------------------------------------------------------------------------
def laporan_keuangan(jurnal, coa=None):
    """Menghitung laba rugi dan neraca sederhana dari saldo buku besar."""
    coa = _coa(coa)
    saldo = saldo_semua_akun(jurnal, coa)

    def per_kategori(kategori):
        hasil = {}
        for akun, s in saldo.items():
            kat, normal = coa[akun]
            if kat == kategori:
                hasil[akun] = s if normal == NORMAL_KATEGORI[kategori] else -s
        return hasil

    pendapatan = per_kategori("Pendapatan")
    beban = per_kategori("Beban")
    aset = per_kategori("Aset")
    liabilitas = per_kategori("Liabilitas")
    ekuitas_akun = per_kategori("Ekuitas")

    total_pendapatan = sum(pendapatan.values())
    total_beban = sum(beban.values())
    laba_bersih = total_pendapatan - total_beban

    ekuitas_akhir = sum(ekuitas_akun.values()) + laba_bersih
    total_aset = sum(aset.values())
    total_liabilitas = sum(liabilitas.values())
    total_liab_ekuitas = total_liabilitas + ekuitas_akhir

    return {
        "pendapatan": pendapatan,
        "beban": beban,
        "total_pendapatan": total_pendapatan,
        "total_beban": total_beban,
        "laba_bersih": laba_bersih,
        "aset": aset,
        "liabilitas": liabilitas,
        "ekuitas_akun": ekuitas_akun,
        "ekuitas_akhir": ekuitas_akhir,
        "total_aset": total_aset,
        "total_liabilitas": total_liabilitas,
        "total_liab_ekuitas": total_liab_ekuitas,
        "seimbang": total_aset == total_liab_ekuitas,
    }


def baris_laba_rugi(lap):
    """Daftar (nama pos, jumlah) untuk Laporan Laba Rugi."""
    baris = [("PENDAPATAN", "")]
    baris += [(a, s) for a, s in lap["pendapatan"].items()]
    baris += [("Total Pendapatan", lap["total_pendapatan"]), ("BEBAN", "")]
    baris += [(a, s) for a, s in lap["beban"].items()]
    baris += [("Total Beban", lap["total_beban"]), ("LABA (RUGI) BERSIH", lap["laba_bersih"])]
    return baris


def baris_posisi_keuangan(lap):
    """Daftar (nama pos, jumlah) untuk Laporan Posisi Keuangan (Neraca)."""
    baris = [("ASET", "")]
    baris += [(a, s) for a, s in lap["aset"].items()]
    baris += [("Total Aset", lap["total_aset"]), ("LIABILITAS", "")]
    baris += [(a, s) for a, s in lap["liabilitas"].items()]
    baris += [("Total Liabilitas", lap["total_liabilitas"]), ("EKUITAS", "")]
    baris += [(a, s) for a, s in lap["ekuitas_akun"].items()]
    baris += [
        ("Laba (Rugi) Bersih", lap["laba_bersih"]),
        ("Total Ekuitas", lap["ekuitas_akhir"]),
        ("Total Liabilitas + Ekuitas", lap["total_liab_ekuitas"]),
    ]
    return baris


def tabel_laporan(baris):
    """Daftar (pos, jumlah) -> DataFrame teks siap tampil."""
    return pd.DataFrame(
        [(p, fmt_angka(j) if j != "" else "") for p, j in baris],
        columns=["Pos", "Jumlah (Rp)"],
    )


def ringkasan_untuk_ai(jurnal, coa=None):
    """Teks ringkasan angka (hasil hitungan Python) yang dikirim ke AI untuk dikomentari."""
    lap = laporan_keuangan(jurnal, coa)
    baris = [f"Jumlah transaksi: {len(jurnal)}", "", "LABA RUGI"]
    for a, s in lap["pendapatan"].items():
        baris.append(f"- {a}: {rp(s)}")
    for a, s in lap["beban"].items():
        baris.append(f"- {a}: {rp(s)}")
    baris += [
        f"Total pendapatan: {rp(lap['total_pendapatan'])}",
        f"Total beban: {rp(lap['total_beban'])}",
        f"Laba (rugi) bersih: {rp(lap['laba_bersih'])}",
        "",
        "POSISI KEUANGAN",
    ]
    for a, s in lap["aset"].items():
        baris.append(f"- Aset {a}: {rp(s)}")
    for a, s in lap["liabilitas"].items():
        baris.append(f"- Liabilitas {a}: {rp(s)}")
    baris += [
        f"Ekuitas akhir (modal + laba - prive): {rp(lap['ekuitas_akhir'])}",
        f"Total aset: {rp(lap['total_aset'])}",
        f"Total liabilitas + ekuitas: {rp(lap['total_liab_ekuitas'])}",
        f"Persamaan akuntansi seimbang: {'Ya' if lap['seimbang'] else 'Tidak'}",
    ]
    return "\n".join(baris)


# ---------------------------------------------------------------------------
# 9. PEMERIKSAAN KESEIMBANGAN & INDIKATOR AKUN (BARU)
# ---------------------------------------------------------------------------
_CATATAN_KHUSUS = {
    "Kas": "Kas negatif: pengeluaran lebih besar dari kas yang tercatat. Mungkin ada setoran/penerimaan yang belum dicatat.",
    "Persediaan": "Persediaan negatif: barang yang dijual melebihi stok yang tercatat. Periksa pembelian barang dagang.",
    "Piutang Usaha": "Piutang negatif: penerimaan lebih besar dari piutang yang tercatat.",
    "Utang Usaha": "Utang negatif: pembayaran lebih besar dari utang yang tercatat.",
}


def pemeriksaan_keseimbangan(jurnal, coa=None):
    """
    Pemeriksaan menyeluruh atas jurnal yang tersimpan:
      - setiap transaksi seimbang,
      - total debit = total kredit (neraca saldo),
      - persamaan akuntansi Aset = Liabilitas + Ekuitas,
      - indikator tiap akun (saldo berlawanan dengan saldo normal = perlu perhatian).
    """
    coa = _coa(coa)
    df = jurnal_ke_df(jurnal)
    total_d = int(df["Debit"].sum()) if not df.empty else 0
    total_k = int(df["Kredit"].sum()) if not df.empty else 0

    tidak_seimbang = []
    for t in jurnal:
        d = sum(b["nominal"] for b in t["baris"] if b["posisi"] == "debit")
        k = sum(b["nominal"] for b in t["baris"] if b["posisi"] == "kredit")
        if d != k:
            tidak_seimbang.append(t["no"])

    lap = laporan_keuangan(jurnal, coa)

    indikator = []
    for akun in akun_terpakai(jurnal, coa):
        _, saldo = buku_besar(jurnal, akun, coa)
        kategori, normal = coa[akun]
        perhatian = saldo < 0
        if perhatian:
            catatan = _CATATAN_KHUSUS.get(
                akun,
                f"Saldo berlawanan dengan saldo normal ({normal}). Periksa kembali pencatatan {akun}.",
            )
        elif saldo == 0:
            catatan = "Saldo nol (impas)."
        else:
            catatan = "Saldo wajar."
        indikator.append({
            "akun": akun, "kategori": kategori, "normal": normal,
            "saldo": saldo, "perhatian": perhatian, "catatan": catatan,
        })

    info = []
    if lap["laba_bersih"] < 0:
        info.append(f"Usaha mencatat rugi bersih {rp(abs(lap['laba_bersih']))} pada periode ini.")
    prive = sum(-v for v in lap["ekuitas_akun"].values() if v < 0)
    modal = sum(v for v in lap["ekuitas_akun"].values() if v > 0)
    if modal and prive > modal:
        info.append("Pengambilan pribadi (prive) lebih besar dari modal yang disetor.")

    return {
        "total_debit": total_d,
        "total_kredit": total_k,
        "transaksi_tidak_seimbang": tidak_seimbang,
        "jurnal_seimbang": not tidak_seimbang and total_d == total_k,
        "persamaan_seimbang": lap["seimbang"],
        "selisih_persamaan": lap["total_aset"] - lap["total_liab_ekuitas"],
        "indikator": indikator,
        "jumlah_perhatian": sum(1 for r in indikator if r["perhatian"]),
        "info": info,
    }


# ---------------------------------------------------------------------------
# 10. SNAPSHOT SESI: EKSPOR & IMPOR (JSON / CSV)  (BARU)
# ---------------------------------------------------------------------------
KOLOM_CSV = ["No", "Tanggal", "Keterangan", "Kode Akun", "Akun", "Kategori", "Saldo Normal", "Debit", "Kredit"]


def buat_snapshot(jurnal, daftar_coa, pengguna="", komentar=""):
    """Kumpulkan data sesi menjadi satu dict yang siap disimpan sebagai JSON."""
    return {
        "aplikasi": "Akun Pintar",
        "versi": VERSI_SNAPSHOT,
        "dibuat": datetime.now().isoformat(timespec="seconds"),
        "pengguna": pengguna,
        "coa": daftar_coa,
        "jurnal": jurnal,
        "komentar": komentar,
    }


def snapshot_ke_json(snapshot):
    return json.dumps(snapshot, ensure_ascii=False, indent=2, default=str)


def jurnal_ke_csv(jurnal, daftar_coa):
    """Jurnal -> CSV (bytes, UTF-8 BOM agar terbuka rapi di Excel) beserta kode/kategori akun."""
    kode = {a["nama"]: a["kode"] for a in daftar_coa}
    peta = coa_ke_peta(daftar_coa)
    df = jurnal_ke_df(jurnal)
    df["Kode Akun"] = df["Akun"].map(kode)
    df["Kategori"] = df["Akun"].map(lambda a: peta[a][0])
    df["Saldo Normal"] = df["Akun"].map(lambda a: peta[a][1])
    return df[KOLOM_CSV].to_csv(index=False).encode("utf-8-sig")


def coa_bersih(daftar):
    """Validasi daftar akun dari file. Return: (daftar_bersih, daftar_error)."""
    if not isinstance(daftar, list) or not daftar:
        return [], ["Daftar akun kosong atau formatnya salah."]
    errors, bersih = [], []
    for i, a in enumerate(daftar, start=1):
        if not isinstance(a, dict):
            errors.append(f"Akun ke-{i}: format salah.")
            continue
        err, kode, nama = periksa_akun(
            bersih, a.get("kode"), a.get("nama"), a.get("kategori"), str(a.get("normal") or "").lower()
        )
        if err:
            errors += [f"Akun ke-{i} ({a.get('nama')}): {e}" for e in err]
            continue
        bersih.append({
            "kode": kode, "nama": nama,
            "kategori": normalisasi_kategori(a["kategori"]), "normal": str(a["normal"]).strip().lower(),
        })
    for inti in sorted(AKUN_INTI):
        ada = next((a for a in bersih if a["nama"] == inti), None)
        if ada is None:
            errors.append(f"Akun inti '{inti}' tidak ada di daftar akun.")
        elif (ada["kategori"], ada["normal"]) != AKUN[inti]:
            errors.append(f"Akun inti '{inti}' harus berkategori {AKUN[inti][0]} dengan saldo normal {AKUN[inti][1]}.")
    return bersih, errors


def jurnal_bersih(jurnal_mentah, coa_peta):
    """Validasi ulang semua transaksi dari file. Return: (jurnal_bersih, daftar_error)."""
    if not isinstance(jurnal_mentah, list):
        return [], ["Data jurnal tidak valid."]
    errors, hasil = [], []
    for no, t in enumerate(jurnal_mentah, start=1):
        if not isinstance(t, dict):
            errors.append(f"Transaksi {no}: format salah.")
            continue
        bersih, err = periksa_transaksi(t, coa_peta)
        if not err:
            try:
                bersih["tanggal"] = pd.to_datetime(t.get("tanggal")).date().isoformat()
            except Exception:
                err.append("Tanggal tidak valid.")
        if err:
            errors += [f"Transaksi {no}: {e}" for e in err]
            continue
        bersih["no"] = len(hasil) + 1
        hasil.append(bersih)
    return hasil, errors


def muat_snapshot_json(teks):
    """
    Baca snapshot JSON. Semua data divalidasi ulang (akun, debit = kredit, tanggal).
    Return: (data, errors). data = {"coa","jurnal","komentar","dibuat","pengguna"} atau None.
    """
    try:
        data = json.loads(teks)
    except json.JSONDecodeError as e:
        return None, [f"File JSON rusak: {e}"]
    if not isinstance(data, dict) or "jurnal" not in data:
        return None, ["Bukan file cadangan Akun Pintar (kunci 'jurnal' tidak ditemukan)."]
    daftar = data.get("coa")
    if daftar is None:
        daftar = coa_default()
    coa_b, err = coa_bersih(daftar)
    if err:
        return None, err
    jur, err = jurnal_bersih(data["jurnal"], coa_ke_peta(coa_b))
    if err:
        return None, err
    return {
        "coa": coa_b,
        "jurnal": jur,
        "komentar": str(data.get("komentar") or ""),
        "dibuat": str(data.get("dibuat") or ""),
        "pengguna": str(data.get("pengguna") or ""),
    }, []


def _nominal_csv(nilai):
    s = str(nilai).strip()
    if not s:
        return 0
    if re.fullmatch(r"\d+(\.0+)?", s):  # '1500000' atau '1500000.0' hasil simpan ulang Excel
        return int(float(s))
    return ke_angka(s)


def muat_snapshot_csv(isi, daftar_coa_sekarang):
    """
    Baca CSV jurnal (format hasil ekspor). Akun yang belum ada di daftar akun
    saat ini ditambahkan otomatis bila kolom Kategori & Saldo Normal tersedia.
    Return: (data, errors).
    """
    try:
        df = pd.read_csv(io.BytesIO(isi), sep=None, engine="python", encoding="utf-8-sig", dtype=str)
        df = df.fillna("")
    except Exception as e:
        return None, [f"File CSV tidak dapat dibaca: {e}"]
    df.columns = [str(c).strip() for c in df.columns]

    wajib = ["No", "Tanggal", "Keterangan", "Akun", "Debit", "Kredit"]
    kurang = [k for k in wajib if k not in df.columns]
    if kurang:
        return None, ["Kolom CSV tidak lengkap, kurang: " + ", ".join(kurang)]

    daftar = [dict(a) for a in daftar_coa_sekarang]
    ada = {a["nama"].lower() for a in daftar}
    punya_meta = {"Kategori", "Saldo Normal"} <= set(df.columns)
    errors = []

    # 1) tambahkan akun baru yang ada di file tetapi belum ada di daftar akun
    for _, r in df.iterrows():
        nama = " ".join(str(r["Akun"]).split())
        if not nama or nama.lower() in ada:
            continue
        ada.add(nama.lower())
        if not punya_meta:
            errors.append(f"Akun '{nama}' belum ada di daftar akun.")
            continue
        kat = normalisasi_kategori(r["Kategori"])
        kode = str(r["Kode Akun"]).strip() if "Kode Akun" in df.columns else ""
        if not kode or kode.lower() in {str(a["kode"]).lower() for a in daftar}:
            kode = kode_berikutnya(daftar, kat)
        err, kode, nama2 = periksa_akun(daftar, kode, nama, kat, str(r["Saldo Normal"]).strip().lower())
        if err:
            errors.append(f"Akun '{nama}': " + " ".join(err))
            continue
        daftar.append({"kode": kode, "nama": nama2, "kategori": kat, "normal": str(r["Saldo Normal"]).strip().lower()})
    if errors:
        return None, errors

    # 2) kelompokkan baris menjadi transaksi (berdasarkan kolom No)
    kelompok = {}
    for idx, r in df.iterrows():
        no = str(r["No"]).strip()
        if not no:
            errors.append(f"Baris {idx + 2}: kolom No kosong.")
            continue
        try:
            d, k = _nominal_csv(r["Debit"]), _nominal_csv(r["Kredit"])
        except (ValueError, TypeError):
            errors.append(f"Baris {idx + 2}: nominal tidak valid.")
            continue
        if d > 0 and k > 0:
            errors.append(f"Baris {idx + 2}: debit dan kredit tidak boleh terisi bersamaan.")
            continue
        if d == 0 and k == 0:
            continue
        t = kelompok.setdefault(no, {"tanggal": str(r["Tanggal"]).strip(), "keterangan": str(r["Keterangan"]).strip(), "baris": []})
        t["baris"].append({
            "akun": str(r["Akun"]).strip(),
            "posisi": "debit" if d > 0 else "kredit",
            "nominal": d if d > 0 else k,
        })
    if errors:
        return None, errors

    jur, err = jurnal_bersih(list(kelompok.values()), coa_ke_peta(daftar))
    if err:
        return None, err
    return {"coa": daftar, "jurnal": jur, "komentar": "", "dibuat": "", "pengguna": ""}, []


# ---------------------------------------------------------------------------
# 11. EKSPOR EXCEL
# ---------------------------------------------------------------------------
def ke_excel(jurnal, coa=None):
    """Semua hasil (jurnal, buku besar, neraca saldo, laporan) -> file Excel (bytes)."""
    lap = laporan_keuangan(jurnal, coa)
    ns, _, _, _ = neraca_saldo(jurnal, coa)

    potongan = []
    for akun in akun_terpakai(jurnal, coa):
        bb, _ = buku_besar(jurnal, akun, coa)
        bb.insert(0, "Akun", akun)
        potongan.append(bb)
    bb_semua = pd.concat(potongan, ignore_index=True) if potongan else pd.DataFrame()

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as penulis:
        jurnal_ke_df(jurnal).to_excel(penulis, sheet_name="Jurnal Umum", index=False)
        bb_semua.to_excel(penulis, sheet_name="Buku Besar", index=False)
        ns.to_excel(penulis, sheet_name="Neraca Saldo", index=False)
        pd.DataFrame(baris_laba_rugi(lap), columns=["Pos", "Jumlah"]).to_excel(
            penulis, sheet_name="Laba Rugi", index=False
        )
        pd.DataFrame(baris_posisi_keuangan(lap), columns=["Pos", "Jumlah"]).to_excel(
            penulis, sheet_name="Posisi Keuangan", index=False
        )

        for ws in penulis.book.worksheets:
            for kolom in ws.columns:
                lebar = max((len(str(c.value)) for c in kolom if c.value is not None), default=8)
                ws.column_dimensions[kolom[0].column_letter].width = min(max(lebar + 2, 10), 45)
                for c in kolom[1:]:
                    if isinstance(c.value, (int, float)):
                        c.number_format = "#,##0"
    return buffer.getvalue()
