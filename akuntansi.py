"""
akuntansi.py
============
Semua logika akuntansi ada di file ini dan dihitung oleh PYTHON, bukan oleh AI.

Prinsipnya:
    - AI hanya membantu MEMAHAMI kalimat transaksi lalu menyusun draf jurnal.
    - Python yang MEMVALIDASI (debit = kredit) dan MENGHITUNG
      (jurnal umum, buku besar, neraca saldo, laporan keuangan).

Alur siklus akuntansi yang diikuti:
    Transaksi -> Jurnal Umum -> Buku Besar -> Neraca Saldo -> Laporan Keuangan
"""

import io
import json
import re

import pandas as pd

# ---------------------------------------------------------------------------
# 1. DAFTAR AKUN (Chart of Accounts)
#    Format:  "Nama Akun": ("Kategori", "Saldo Normal")
#    AI HANYA boleh memilih akun dari daftar ini. Mau tambah akun? Cukup tambah
#    satu baris di sini.
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
URUTAN_AKUN = list(AKUN.keys())
_AKUN_LOWER = {nama.lower(): nama for nama in AKUN}


def daftar_akun_df():
    """Tabel daftar akun untuk ditampilkan di sidebar."""
    return pd.DataFrame(
        [{"Akun": a, "Kategori": k, "Saldo Normal": s.capitalize()} for a, (k, s) in AKUN.items()]
    )


# ---------------------------------------------------------------------------
# 2. FORMAT UANG
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
        # "1,5 juta" / "1.5 juta": koma/titik dianggap desimal
        angka = angka.replace(",", ".")
        if angka.count(".") > 1:
            angka = angka.replace(".", "")
        return int(round(float(angka) * pengali))

    # Tanpa satuan: titik/koma dianggap pemisah ribuan ("1.500.000")
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
# 3. VALIDASI TRANSAKSI  (INI TUGAS PYTHON, BUKAN AI)
#    Bentuk satu transaksi:
#    {"tanggal": "2026-11-26", "keterangan": "Beli perlengkapan",
#     "baris": [{"akun": "Perlengkapan", "posisi": "debit",  "nominal": 500000},
#               {"akun": "Kas",          "posisi": "kredit", "nominal": 500000}]}
# ---------------------------------------------------------------------------
def periksa_transaksi(transaksi):
    """
    Membersihkan dan memvalidasi satu transaksi.
    Return: (transaksi_bersih, daftar_error). Jika daftar_error kosong -> valid.
    """
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
        # --- akun harus ada di daftar akun
        nama = str(b.get("akun") or "").strip()
        nama_resmi = _AKUN_LOWER.get(nama.lower())
        if not nama_resmi:
            errors.append(f"Baris {i}: akun '{nama}' tidak ada di daftar akun.")
            continue

        # --- posisi harus debit / kredit
        posisi = str(b.get("posisi") or "").strip().lower()
        if posisi not in ("debit", "kredit"):
            errors.append(f"Baris {i}: posisi '{posisi}' harus 'debit' atau 'kredit'.")
            continue

        # --- nominal harus angka positif
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
# 4. JURNAL UMUM
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


# ---------------------------------------------------------------------------
# 5. BUKU BESAR
# ---------------------------------------------------------------------------
def akun_terpakai(jurnal):
    """Akun yang muncul di jurnal, diurutkan sesuai daftar akun."""
    df = jurnal_ke_df(jurnal)
    dipakai = set(df["Akun"]) if not df.empty else set()
    return [a for a in URUTAN_AKUN if a in dipakai]


def buku_besar(jurnal, akun):
    """
    Mutasi satu akun beserta saldo berjalan.
    Saldo mengikuti saldo normal akun:
        saldo normal debit  -> saldo = debit - kredit
        saldo normal kredit -> saldo = kredit - debit
    Return: (DataFrame, saldo_akhir)
    """
    df = jurnal_ke_df(jurnal)
    df = df[df["Akun"] == akun].copy()
    normal = AKUN[akun][1]
    if normal == "debit":
        df["Saldo"] = (df["Debit"] - df["Kredit"]).cumsum()
    else:
        df["Saldo"] = (df["Kredit"] - df["Debit"]).cumsum()
    df = df[["Tanggal", "No", "Keterangan", "Debit", "Kredit", "Saldo"]].rename(
        columns={"No": "No. Jurnal"}
    )
    saldo_akhir = int(df["Saldo"].iloc[-1]) if not df.empty else 0
    return df.reset_index(drop=True), saldo_akhir


def saldo_semua_akun(jurnal):
    """Dictionary {akun: saldo} (positif = di sisi saldo normal)."""
    hasil = {}
    for akun in akun_terpakai(jurnal):
        _, saldo = buku_besar(jurnal, akun)
        hasil[akun] = saldo
    return hasil


# ---------------------------------------------------------------------------
# 6. NERACA SALDO
# ---------------------------------------------------------------------------
def neraca_saldo(jurnal):
    """
    Neraca saldo: saldo akhir tiap akun diletakkan di kolom Debit atau Kredit.
    Return: (DataFrame, total_debit, total_kredit, seimbang)
    """
    df = jurnal_ke_df(jurnal)
    baris = []
    for akun in akun_terpakai(jurnal):
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
# 7. LAPORAN KEUANGAN (laba rugi + posisi keuangan)
# ---------------------------------------------------------------------------
def laporan_keuangan(jurnal):
    """Menghitung laba rugi dan neraca sederhana dari saldo buku besar."""
    saldo = saldo_semua_akun(jurnal)

    def per_kategori(kategori):
        return {a: s for a, s in saldo.items() if AKUN[a][0] == kategori}

    pendapatan = per_kategori("Pendapatan")
    beban = per_kategori("Beban")
    aset = per_kategori("Aset")
    liabilitas = per_kategori("Liabilitas")

    total_pendapatan = sum(pendapatan.values())
    total_beban = sum(beban.values())
    laba_bersih = total_pendapatan - total_beban

    modal = saldo.get("Modal Pemilik", 0)
    prive = saldo.get("Prive", 0)
    ekuitas_akhir = modal + laba_bersih - prive

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
        "modal": modal,
        "prive": prive,
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
    baris += [
        ("Total Liabilitas", lap["total_liabilitas"]),
        ("EKUITAS", ""),
        ("Modal Pemilik", lap["modal"]),
        ("Laba (Rugi) Bersih", lap["laba_bersih"]),
        ("Prive", -lap["prive"]),
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


def ringkasan_untuk_ai(jurnal):
    """Teks ringkasan angka (hasil hitungan Python) yang dikirim ke AI untuk dikomentari."""
    lap = laporan_keuangan(jurnal)
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
# 8. EKSPOR EXCEL
# ---------------------------------------------------------------------------
def ke_excel(jurnal):
    """Semua hasil (jurnal, buku besar, neraca saldo, laporan) -> file Excel (bytes)."""
    lap = laporan_keuangan(jurnal)
    ns, _, _, _ = neraca_saldo(jurnal)

    # Buku besar semua akun ditumpuk dalam satu sheet
    potongan = []
    for akun in akun_terpakai(jurnal):
        bb, _ = buku_besar(jurnal, akun)
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

        # Rapikan: lebar kolom + format ribuan
        for ws in penulis.book.worksheets:
            for kolom in ws.columns:
                lebar = max((len(str(c.value)) for c in kolom if c.value is not None), default=8)
                ws.column_dimensions[kolom[0].column_letter].width = min(max(lebar + 2, 10), 45)
                for c in kolom[1:]:
                    if isinstance(c.value, (int, float)):
                        c.number_format = "#,##0"
    return buffer.getvalue()
