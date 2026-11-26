"""
JurnalAI - Asisten Jurnal Otomatis dari Kalimat Biasa
=====================================================
Alur:
    Kalimat transaksi -> AI menyusun draf jurnal -> Python memvalidasi (debit = kredit)
    -> pengguna meninjau/mengedit -> Jurnal Umum -> Buku Besar -> Neraca Saldo
    -> Laporan Keuangan -> Ekspor Excel

Pembagian tugas:
    AI     : memahami kalimat, memilih akun, menulis komentar
    Python : validasi, buku besar, neraca saldo, laporan (lihat akuntansi.py)
"""

import os
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from groq import Groq

import akuntansi as ak

# ---------------------------------------------------------------------------
# PENGATURAN HALAMAN
# ---------------------------------------------------------------------------
st.set_page_config(page_title="JurnalAI", page_icon="📒", layout="wide")

# Model LLM di Groq. Untuk ganti model, copy "Model ID" dari
# https://console.groq.com/docs/models lalu tempel di sini.
MODEL = "openai/gpt-oss-20b"

# ---------------------------------------------------------------------------
# API KEY (aman: dari .env atau Streamlit Secrets, jangan ditulis di kode)
# ---------------------------------------------------------------------------
load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    try:
        GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
    except Exception:
        GROQ_API_KEY = None

if not GROQ_API_KEY:
    st.error("🚨 API Key belum diatur! Isi GROQ_API_KEY di Streamlit Secrets atau file .env.")
    st.stop()

client = Groq(api_key=GROQ_API_KEY)

# ---------------------------------------------------------------------------
# PROMPT UNTUK AI
# ---------------------------------------------------------------------------
PROMPT_TEMPLATE = """Kamu adalah asisten akuntansi yang mengubah kalimat transaksi menjadi jurnal umum (double-entry).

DAFTAR AKUN (gunakan HANYA nama akun ini, persis sama penulisannya):
{{DAFTAR_AKUN}}

ATURAN:
1. Setiap transaksi: total debit HARUS sama dengan total kredit.
2. Nominal berupa bilangan bulat rupiah tanpa titik, koma, atau simbol (contoh: 500000).
3. Satu pesan boleh berisi beberapa transaksi (satu per baris/kalimat). Buat satu objek transaksi untuk tiap transaksi, urut sesuai input.
4. Transaksi campuran (sebagian tunai, sebagian kredit) dicatat dalam jurnal dengan lebih dari 2 baris.
5. Penjualan barang dagang: debit Kas (tunai) atau Piutang Usaha (kredit), kredit Penjualan. HANYA jika harga pokok disebutkan, tambahkan juga debit Beban Pokok Penjualan dan kredit Persediaan.
6. Pembelian secara kredit/utang -> kredit Utang Usaha. Setoran modal pemilik -> kredit Modal Pemilik. Pemilik mengambil uang atau barang untuk keperluan pribadi -> debit Prive.
7. JANGAN MENEBAK. Jika ada informasi penting yang tidak jelas (nominal tidak pasti, tidak jelas tunai atau kredit, jenis barang ambigu antara peralatan/perlengkapan/beban), jawab dengan status "tanya" berisi SATU pertanyaan singkat dalam bahasa Indonesia.
8. tanggal: format YYYY-MM-DD jika disebut dalam kalimat, jika tidak isi null.
9. Jawab HANYA dengan JSON, tanpa teks lain dan tanpa markdown.

FORMAT JIKA TRANSAKSI JELAS:
{"status":"ok","pertanyaan":"","transaksi":[{"tanggal":null,"keterangan":"Beli perlengkapan tunai","baris":[{"akun":"Perlengkapan","posisi":"debit","nominal":500000},{"akun":"Kas","posisi":"kredit","nominal":500000}]}]}

FORMAT JIKA PERLU BERTANYA:
{"status":"tanya","pertanyaan":"Pembelian peralatan Rp2.000.000 dibayar tunai atau secara kredit?","transaksi":[]}
"""


def buat_prompt_sistem():
    daftar = "\n".join(f"- {a} ({k}, saldo normal {s})" for a, (k, s) in ak.AKUN.items())
    return PROMPT_TEMPLATE.replace("{{DAFTAR_AKUN}}", daftar)


CONTOH = (
    "Pak Budi menyetor modal Rp10.000.000 tunai\n"
    "Beli perlengkapan Rp500.000 tunai\n"
    "Beli barang dagang Rp3.000.000 secara kredit dari CV Maju\n"
    "Jual barang tunai Rp2.500.000, harga pokoknya Rp1.500.000\n"
    "Bayar gaji karyawan Rp800.000\n"
    "Pak Budi mengambil uang usaha Rp100.000 untuk keperluan pribadi"
)


# ---------------------------------------------------------------------------
# AGENT: AI menyusun jurnal -> Python memvalidasi -> kalau salah, AI memperbaiki
# ---------------------------------------------------------------------------
def tanggal_aman(nilai, default):
    """Ubah tanggal dari AI jadi 'YYYY-MM-DD'; kalau tidak valid pakai tanggal default."""
    if not nilai:
        return default
    try:
        return pd.to_datetime(nilai).date().isoformat()
    except Exception:
        return default


def jalankan_agent(teks, tanggal_default, maks_ulang=2):
    """
    Return: (hasil, log)
        hasil["status"] = "ok"    -> hasil["transaksi"] berisi draf jurnal valid
                        = "tanya" -> hasil["pertanyaan"] berisi pertanyaan agent
                        = "gagal" -> hasil["pesan"] berisi penyebab
    """
    log = []
    pesan = [
        {"role": "system", "content": buat_prompt_sistem()},
        {"role": "user", "content": teks},
    ]

    for percobaan in range(1, maks_ulang + 2):
        respons = client.chat.completions.create(model=MODEL, messages=pesan, temperature=0)
        isi = respons.choices[0].message.content or ""
        log.append(f"Percobaan {percobaan}: AI menyusun draf jurnal.")

        masalah = []
        try:
            data = ak.parse_json_ai(isi)
        except ValueError as e:
            masalah.append(str(e))
        else:
            if data.get("status") == "tanya":
                log.append("AI meminta klarifikasi karena informasi kurang jelas.")
                return {
                    "status": "tanya",
                    "pertanyaan": data.get("pertanyaan") or "Mohon perjelas transaksinya.",
                }, log

            hasil = []
            for no, t in enumerate(data.get("transaksi") or [], start=1):
                bersih, error = ak.periksa_transaksi(t)
                if error:
                    masalah += [f"Transaksi {no}: {e}" for e in error]
                else:
                    bersih["tanggal"] = tanggal_aman(bersih["tanggal"], tanggal_default)
                    hasil.append(bersih)
            if not masalah and not hasil:
                masalah.append("Tidak ada transaksi yang terbaca.")

            if not masalah:
                log.append("Python: validasi lolos (debit = kredit, akun sesuai daftar).")
                return {"status": "ok", "transaksi": hasil}, log

        log.append("Python: validasi GAGAL -> " + " | ".join(masalah))
        pesan.append({"role": "assistant", "content": isi or "(kosong)"})
        pesan.append({
            "role": "user",
            "content": "Validasi Python menemukan masalah:\n- " + "\n- ".join(masalah)
            + "\nPerbaiki, lalu kirim ulang JSON lengkap (semua transaksi).",
        })

    return {"status": "gagal", "pesan": "AI belum berhasil menyusun jurnal yang valid. Coba perjelas kalimatnya."}, log


def buat_komentar(jurnal):
    """AI menulis komentar atas angka yang SUDAH dihitung Python."""
    respons = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Kamu adalah asisten akuntansi. Kamu menerima ringkasan laporan keuangan sederhana "
                    "yang SUDAH dihitung. Gunakan hanya angka yang diberikan; jangan menghitung ulang "
                    "atau mengarang angka baru. Jawab dalam bahasa Indonesia, maksimal 200 kata, dengan "
                    "tiga bagian: Gambaran Umum, Hal yang Perlu Diperhatikan, dan Saran. Ingatkan singkat "
                    "bahwa laporan ini hanya berdasarkan transaksi yang diinput."
                ),
            },
            {"role": "user", "content": ak.ringkasan_untuk_ai(jurnal)},
        ],
        temperature=0.3,
    )
    return respons.choices[0].message.content


# ---------------------------------------------------------------------------
# STATE (data yang diingat selama aplikasi dibuka)
# ---------------------------------------------------------------------------
STATE_AWAL = {
    "jurnal": [],            # transaksi yang sudah disetujui
    "draf": [],              # draf dari AI yang menunggu persetujuan
    "draf_versi": 0,         # penanda agar editor draf baru selalu segar
    "pertanyaan": "",        # pertanyaan klarifikasi dari agent
    "input_terakhir": "",
    "tanggal_terakhir": date.today().isoformat(),
    "log": [],
    "komentar": "",
    "pesan_sukses": "",
    "teks_input": "",
}
for kunci, nilai in STATE_AWAL.items():
    if kunci not in st.session_state:
        st.session_state[kunci] = nilai

if st.session_state.pop("kosongkan_input", False):
    st.session_state.teks_input = ""


def isi_contoh():
    st.session_state.teks_input = CONTOH


def proses_teks(teks, tanggal_default):
    """Panggil agent lalu simpan hasilnya di state. Return status."""
    with st.spinner("🤖 AI sedang menyusun jurnal..."):
        try:
            hasil, log = jalankan_agent(teks, tanggal_default)
        except Exception as e:
            st.error(f"Gagal menghubungi AI: {e}")
            return "gagal"

    st.session_state.log = log
    st.session_state.input_terakhir = teks
    st.session_state.tanggal_terakhir = tanggal_default

    if hasil["status"] == "ok":
        st.session_state.draf = hasil["transaksi"]
        st.session_state.draf_versi += 1
        st.session_state.pertanyaan = ""
    elif hasil["status"] == "tanya":
        st.session_state.draf = []
        st.session_state.pertanyaan = hasil["pertanyaan"]
    else:
        st.session_state.draf = []
        st.session_state.pertanyaan = ""
        st.error(hasil["pesan"])
    return hasil["status"]


# ---------------------------------------------------------------------------
# TAMPILAN UTAMA
# ---------------------------------------------------------------------------
st.title("📒 JurnalAI – Asisten Jurnal Otomatis dari Kalimat Biasa")
st.write(
    "Ketik transaksi dengan bahasa sehari-hari. **AI** menyusun jurnal, sedangkan **Python** "
    "memvalidasi dan menghitung buku besar, neraca saldo, dan laporan keuangan."
)

with st.sidebar:
    st.header("ℹ️ Cara Kerja")
    st.markdown(
        "1. Ketik transaksi\n"
        "2. AI menyusun draf jurnal\n"
        "3. Python cek debit = kredit\n"
        "4. Kamu tinjau & setujui\n"
        "5. Buku besar, neraca saldo, dan laporan terbentuk otomatis\n"
        "6. Unduh hasil ke Excel"
    )
    st.caption(f"Model AI: `{MODEL}`")
    with st.expander("📚 Daftar Akun"):
        st.dataframe(ak.daftar_akun_df(), hide_index=True)

if st.session_state.pesan_sukses:
    st.success(st.session_state.pesan_sukses)
    st.session_state.pesan_sukses = ""

jurnal = st.session_state.jurnal

# Ringkasan atas
m1, m2, m3 = st.columns(3)
m1.metric("Jumlah transaksi", len(jurnal))
if jurnal:
    _, total_d, total_k, seimbang = ak.neraca_saldo(jurnal)
    m2.metric("Total debit = kredit", ak.rp(total_d))
    m3.metric("Neraca saldo", "✅ Seimbang" if seimbang else "❌ Tidak seimbang")
else:
    m2.metric("Total debit = kredit", "Rp0")
    m3.metric("Neraca saldo", "—")

tab_input, tab_jurnal, tab_bb, tab_ns, tab_lap, tab_ekspor = st.tabs(
    ["✍️ Input Transaksi", "📒 Jurnal Umum", "📚 Buku Besar", "⚖️ Neraca Saldo", "📑 Laporan Keuangan", "📥 Ekspor"]
)

# ======================= TAB 1: INPUT TRANSAKSI =======================
with tab_input:
    kiri, kanan = st.columns([3, 1])
    with kanan:
        tanggal_default = st.date_input("Tanggal (jika tidak disebut di kalimat)", value=date.today())
        st.button("📋 Isi contoh transaksi", on_click=isi_contoh)
    with kiri:
        teks = st.text_area(
            "✍️ Ketik transaksi (satu transaksi per baris)",
            key="teks_input",
            height=180,
            placeholder="Contoh: Beli perlengkapan Rp500.000 tunai",
        )
        proses = st.button("🤖 Proses dengan AI", type="primary")

    if proses:
        if not teks.strip():
            st.warning("Ketik dulu transaksinya.")
        else:
            proses_teks(teks.strip(), tanggal_default.isoformat())

    # --- Agent bertanya balik (klarifikasi)
    if st.session_state.pertanyaan:
        st.info(f"🤔 **Agent bertanya:** {st.session_state.pertanyaan}")
        with st.form("form_jawab", clear_on_submit=True):
            jawaban = st.text_input("Jawabanmu")
            kirim = st.form_submit_button("Kirim jawaban")
        if kirim and jawaban.strip():
            gabungan = (
                f"{st.session_state.input_terakhir}\n\n"
                f"(Pertanyaan agent: {st.session_state.pertanyaan}\nJawaban pengguna: {jawaban.strip()})"
            )
            status = proses_teks(gabungan, st.session_state.tanggal_terakhir)
            if status != "gagal":
                st.rerun()

    # --- Tinjau draf (human-in-the-loop)
    if st.session_state.draf:
        st.subheader("📝 Tinjau Draf Jurnal")
        st.caption("Periksa akun dan nominalnya. Kamu boleh mengedit sebelum menyimpan.")

        hasil_edit = []
        for i, t in enumerate(st.session_state.draf):
            kunci = f"{st.session_state.draf_versi}_{i}"
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                ket = c1.text_input("Keterangan", value=t["keterangan"], key=f"ket_{kunci}")
                tgl = c2.date_input(
                    "Tanggal", value=date.fromisoformat(t["tanggal"]), key=f"tgl_{kunci}"
                )
                df_awal = pd.DataFrame(
                    [{"Akun": b["akun"], "Posisi": b["posisi"], "Nominal": b["nominal"]} for b in t["baris"]]
                )
                df_edit = st.data_editor(
                    df_awal,
                    key=f"edit_{kunci}",
                    num_rows="dynamic",
                    hide_index=True,
                    column_config={
                        "Akun": st.column_config.SelectboxColumn("Akun", options=list(ak.AKUN.keys()), required=True),
                        "Posisi": st.column_config.SelectboxColumn("Posisi", options=["debit", "kredit"], required=True),
                        "Nominal": st.column_config.NumberColumn("Nominal (Rp)", min_value=0, step=1000, format="%d"),
                    },
                )
                d = df_edit.loc[df_edit["Posisi"] == "debit", "Nominal"].sum()
                k = df_edit.loc[df_edit["Posisi"] == "kredit", "Nominal"].sum()
                if d == k and d > 0:
                    st.success(f"✅ Seimbang: debit {ak.rp(d)} = kredit {ak.rp(k)}")
                else:
                    st.error(f"❌ Belum seimbang: debit {ak.rp(d)} ≠ kredit {ak.rp(k)}")
            hasil_edit.append((ket, tgl, df_edit))

        b1, b2, _ = st.columns([1.2, 1, 3])
        if b1.button("✅ Setuju & simpan", type="primary"):
            baru, semua_error = [], []
            for no, (ket, tgl, df_edit) in enumerate(hasil_edit, start=1):
                baris = []
                for _, r in df_edit.iterrows():
                    if pd.isna(r["Akun"]) or pd.isna(r["Nominal"]):
                        continue
                    baris.append({
                        "akun": r["Akun"],
                        "posisi": r["Posisi"] if pd.notna(r["Posisi"]) else "",
                        "nominal": r["Nominal"],
                    })
                bersih, error = ak.periksa_transaksi(
                    {"tanggal": tgl.isoformat(), "keterangan": ket, "baris": baris}
                )
                if error:
                    semua_error += [f"Transaksi {no}: {e}" for e in error]
                else:
                    baru.append(bersih)

            if semua_error:
                st.error("Belum bisa disimpan:\n\n" + "\n".join(f"- {e}" for e in semua_error))
            else:
                for bersih in baru:
                    bersih["no"] = len(st.session_state.jurnal) + 1
                    st.session_state.jurnal.append(bersih)
                st.session_state.draf = []
                st.session_state.input_terakhir = ""
                st.session_state.kosongkan_input = True
                st.session_state.komentar = ""
                st.session_state.pesan_sukses = f"✅ {len(baru)} transaksi disimpan ke Jurnal Umum."
                st.rerun()

        if b2.button("🗑️ Buang draf"):
            st.session_state.draf = []
            st.rerun()

    if st.session_state.log:
        with st.expander("🔍 Jejak kerja agent (untuk transparansi)"):
            for baris_log in st.session_state.log:
                st.write(f"- {baris_log}")

# ======================= TAB 2: JURNAL UMUM =======================
with tab_jurnal:
    if not jurnal:
        st.info("Belum ada transaksi. Mulai dari tab **Input Transaksi**.")
    else:
        st.subheader("📒 Jurnal Umum")
        tampil = ak.jurnal_tampil_df(jurnal)
        st.dataframe(
            tampil.style.format({"Debit": ak.fmt_kosong, "Kredit": ak.fmt_kosong}),
            hide_index=True,
        )
        c1, c2, _ = st.columns([1.3, 1.2, 3])
        if c1.button("↩️ Hapus transaksi terakhir"):
            st.session_state.jurnal.pop()
            st.session_state.komentar = ""
            st.rerun()
        if c2.button("🗑️ Hapus semua jurnal"):
            st.session_state.jurnal = []
            st.session_state.komentar = ""
            st.rerun()

# ======================= TAB 3: BUKU BESAR =======================
with tab_bb:
    if not jurnal:
        st.info("Buku besar terbentuk otomatis setelah ada transaksi.")
    else:
        st.subheader("📚 Buku Besar")
        akun_pilih = st.selectbox("Pilih akun", ak.akun_terpakai(jurnal))
        df_bb, saldo_akhir = ak.buku_besar(jurnal, akun_pilih)
        kategori, normal = ak.AKUN[akun_pilih]
        st.caption(f"Kategori: {kategori} · Saldo normal: {normal}")
        st.metric(f"Saldo akhir {akun_pilih}", ak.rp(saldo_akhir))
        st.dataframe(
            df_bb.style.format({"Debit": ak.fmt_kosong, "Kredit": ak.fmt_kosong, "Saldo": ak.fmt_angka}),
            hide_index=True,
        )

# ======================= TAB 4: NERACA SALDO =======================
with tab_ns:
    if not jurnal:
        st.info("Neraca saldo terbentuk otomatis setelah ada transaksi.")
    else:
        st.subheader("⚖️ Neraca Saldo")
        ns, total_d, total_k, seimbang = ak.neraca_saldo(jurnal)
        ns_tampil = pd.concat(
            [ns, pd.DataFrame([{"Akun": "TOTAL", "Debit": total_d, "Kredit": total_k}])],
            ignore_index=True,
        )
        st.dataframe(
            ns_tampil.style.format({"Debit": ak.fmt_kosong, "Kredit": ak.fmt_kosong}),
            hide_index=True,
        )
        if seimbang:
            st.success(f"✅ Seimbang: total debit {ak.rp(total_d)} = total kredit {ak.rp(total_k)}")
        else:
            st.error(f"❌ Tidak seimbang: debit {ak.rp(total_d)} ≠ kredit {ak.rp(total_k)}")

# ======================= TAB 5: LAPORAN KEUANGAN =======================
with tab_lap:
    if not jurnal:
        st.info("Laporan keuangan terbentuk otomatis setelah ada transaksi.")
    else:
        lap = ak.laporan_keuangan(jurnal)
        st.subheader("📑 Laporan Keuangan Sederhana")

        x1, x2, x3 = st.columns(3)
        x1.metric("Total pendapatan", ak.rp(lap["total_pendapatan"]))
        x2.metric("Total beban", ak.rp(lap["total_beban"]))
        x3.metric("Laba (rugi) bersih", ak.rp(lap["laba_bersih"]))

        kiri, kanan = st.columns(2)
        with kiri:
            st.markdown("**Laporan Laba Rugi**")
            st.dataframe(ak.tabel_laporan(ak.baris_laba_rugi(lap)), hide_index=True)
        with kanan:
            st.markdown("**Laporan Posisi Keuangan (Neraca)**")
            st.dataframe(ak.tabel_laporan(ak.baris_posisi_keuangan(lap)), hide_index=True)

        if lap["seimbang"]:
            st.success("✅ Persamaan akuntansi seimbang: Aset = Liabilitas + Ekuitas")
        else:
            st.error("❌ Persamaan akuntansi tidak seimbang. Periksa jurnal.")

        df_grafik = pd.DataFrame({
            "Pos": ["Pendapatan", "Beban", "Laba (Rugi) Bersih"],
            "Jumlah": [lap["total_pendapatan"], lap["total_beban"], lap["laba_bersih"]],
        })
        fig = px.bar(df_grafik, x="Pos", y="Jumlah", color="Pos", text_auto=".3s", title="Ringkasan Laba Rugi")
        st.plotly_chart(fig)

        st.markdown("### 🤖 Komentar AI")
        if st.button("Buat komentar AI"):
            with st.spinner("AI sedang menulis komentar..."):
                try:
                    st.session_state.komentar = buat_komentar(jurnal)
                except Exception as e:
                    st.error(f"Gagal menghubungi AI: {e}")
        if st.session_state.komentar:
            st.write(st.session_state.komentar)
            st.caption("Komentar ini ditulis AI dari angka yang dihitung Python. Tetap periksa kembali.")

# ======================= TAB 6: EKSPOR =======================
with tab_ekspor:
    if not jurnal:
        st.info("Belum ada data untuk diunduh.")
    else:
        st.subheader("📥 Unduh Hasil")
        st.write("File Excel berisi: Jurnal Umum, Buku Besar, Neraca Saldo, Laba Rugi, dan Posisi Keuangan.")
        st.download_button(
            "📥 Unduh Excel",
            data=ak.ke_excel(jurnal),
            file_name="jurnalai_hasil.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.caption("Data hanya tersimpan selama aplikasi dibuka. Unduh dulu sebelum menutup halaman.")
