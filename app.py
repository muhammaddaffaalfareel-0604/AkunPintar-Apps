"""
Akun Pintar - Asisten Jurnal Otomatis dari Kalimat Biasa
=========================================================
Alur:
    Masuk/Daftar -> Input transaksi -> AI menyusun draf jurnal -> Python memvalidasi
    (debit = kredit) -> pengguna meninjau -> Jurnal Umum -> Buku Besar -> Neraca Saldo
    -> Laporan Keuangan -> Ekspor Excel

Pembagian tugas:
    AI     : memahami kalimat, memilih akun, menulis komentar
    Python : validasi, buku besar, neraca saldo, laporan (lihat akuntansi.py)

Catatan keamanan: API key HANYA dibaca dari st.secrets / environment, tidak ada di kode.
"""

import hashlib
import hmac
import html
import json
import os
import re
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
st.set_page_config(page_title="Akun Pintar", page_icon="🌿", layout="wide")

MODEL = "openai/gpt-oss-20b"

MENU = [
    "🏠 Dashboard",
    "✍️ Input Transaksi",
    "📒 Jurnal Umum",
    "📚 Buku Besar",
    "⚖️ Neraca Saldo",
    "📑 Laporan Keuangan",
    "📥 Ekspor Excel",
]
M_DASHBOARD, M_INPUT, M_JURNAL, M_BB, M_NS, M_LAP, M_EKSPOR = MENU

HIJAU = ["#047857", "#10b981", "#34d399", "#6ee7b7", "#a7f3d0", "#065f46"]

# ---------------------------------------------------------------------------
# CSS KUSTOM (hijau & putih; hanya menyentuh elemen yang aman)
# ---------------------------------------------------------------------------
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
:root{
  --hijau:#059669; --hijau-tua:#065f46; --hijau-muda:#ecfdf5;
  --garis:#cdeedd; --teks:#0f2a1d; --abu:#55675d;
}
.stApp{font-family:'Plus Jakarta Sans',system-ui,-apple-system,sans-serif;background:#f6fbf8;color:var(--teks);}
.block-container{padding-top:1.8rem;padding-bottom:3rem;max-width:1240px;}
footer{visibility:hidden;}
h1,h2,h3,h4{color:var(--hijau-tua);letter-spacing:-0.01em;}

/* Sidebar */
[data-testid="stSidebar"]{background:#ffffff;border-right:1px solid var(--garis);}
[data-testid="stSidebar"] .stButton>button{width:100%;justify-content:flex-start;text-align:left;}
.brand{font-size:1.4rem;font-weight:800;color:var(--hijau-tua);letter-spacing:-0.02em;}
.brand-sub{color:var(--abu);font-size:.82rem;margin:.1rem 0 1rem;}
.user-chip{display:flex;gap:.7rem;align-items:center;padding:.7rem .8rem;background:var(--hijau-muda);
  border:1px solid var(--garis);border-radius:12px;margin-bottom:1rem;}
.user-chip b{color:var(--hijau-tua);}
.user-chip span{color:var(--abu);font-size:.8rem;}
.avatar{min-width:38px;height:38px;border-radius:50%;background:var(--hijau);color:#fff;
  display:flex;align-items:center;justify-content:center;font-weight:700;}

/* Tombol */
.stButton>button,.stDownloadButton>button,.stFormSubmitButton>button{
  border-radius:10px;font-weight:600;border:1px solid var(--garis);background:#fff;color:var(--hijau-tua);}
.stButton>button[kind="secondary"]:hover{border-color:var(--hijau);background:var(--hijau-muda);}
.stButton>button[kind="primary"],.stDownloadButton>button[kind="primary"],
.stFormSubmitButton>button[kind="primaryFormSubmit"]{background:var(--hijau);border:1px solid var(--hijau);color:#fff;}
.stButton>button[kind="primary"] p,.stDownloadButton>button[kind="primary"] p,
.stFormSubmitButton>button[kind="primaryFormSubmit"] p{color:#fff;}
.stButton>button[kind="primary"]:hover,.stDownloadButton>button[kind="primary"]:hover,
.stFormSubmitButton>button[kind="primaryFormSubmit"]:hover{background:var(--hijau-tua);border-color:var(--hijau-tua);}

/* Kartu metrik, tabel, tab, expander */
[data-testid="stMetric"]{background:#fff;border:1px solid var(--garis);border-radius:14px;padding:14px 18px;}
[data-testid="stMetricLabel"]{color:var(--abu);}
[data-testid="stMetricValue"]{color:var(--hijau-tua);font-weight:700;}
[data-testid="stDataFrame"]{border:1px solid var(--garis);border-radius:12px;overflow:hidden;}
[data-testid="stExpander"]{background:#fff;border:1px solid var(--garis);border-radius:12px;}
button[data-baseweb="tab"][aria-selected="true"]{color:var(--hijau-tua);}
[data-baseweb="tab-highlight"]{background-color:var(--hijau);}

/* Komponen buatan sendiri */
.judul{margin:0 0 1.1rem;}
.judul h2{margin:0;font-size:1.65rem;font-weight:800;}
.judul p{margin:.25rem 0 0;color:var(--abu);}
.hero{background:var(--hijau-tua);color:#fff;border-radius:16px;padding:1.5rem 1.8rem;margin-bottom:1.2rem;}
.hero h1{color:#fff;margin:0;font-size:1.8rem;font-weight:800;}
.hero p{margin:.4rem 0 0;color:#d1fae5;}
.kartu{background:#fff;border:1px solid var(--garis);border-radius:14px;padding:1.1rem 1.3rem;margin-bottom:1rem;}
.kartu h4{margin:0 0 .25rem;}
.kartu p{margin:0;color:var(--abu);}
</style>
"""


def pasang_css():
    st.markdown(CSS, unsafe_allow_html=True)


def judul(ikon, teks, sub=""):
    st.markdown(
        f'<div class="judul"><h2>{ikon} {html.escape(teks)}</h2><p>{html.escape(sub)}</p></div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# API KEY & KLIEN (tidak ada hardcoded key; di-cache supaya klien dibuat sekali)
# ---------------------------------------------------------------------------
load_dotenv()


@st.cache_resource
def get_client():
    """Return klien Groq, atau None jika GROQ_API_KEY belum diatur."""
    kunci = os.getenv("GROQ_API_KEY")
    if not kunci:
        try:
            kunci = st.secrets["GROQ_API_KEY"]
        except Exception:
            kunci = None
    return Groq(api_key=kunci) if kunci else None


# ---------------------------------------------------------------------------
# PROMPT UNTUK AI (tidak berubah)
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

CONTOH_BAWAAN = (
    "Pak Budi menyetor modal Rp10.000.000 tunai\n"
    "Beli perlengkapan Rp500.000 tunai\n"
    "Beli barang dagang Rp3.000.000 secara kredit dari CV Maju\n"
    "Jual barang tunai Rp2.500.000, harga pokoknya Rp1.500.000\n"
    "Bayar gaji karyawan Rp800.000\n"
    "Pak Budi mengambil uang usaha Rp100.000 untuk keperluan pribadi"
)


# ---------------------------------------------------------------------------
# DATA STATIS & HITUNGAN (di-cache agar ringan di Streamlit Community Cloud)
# ---------------------------------------------------------------------------
@st.cache_data
def buat_prompt_sistem():
    daftar = "\n".join(f"- {a} ({k}, saldo normal {s})" for a, (k, s) in ak.AKUN.items())
    return PROMPT_TEMPLATE.replace("{{DAFTAR_AKUN}}", daftar)


@st.cache_data
def daftar_akun():
    return ak.daftar_akun_df()


@st.cache_data
def muat_contoh():
    """Baca contoh_transaksi.txt (hanya bagian sebelum baris '---'); jika tidak ada pakai bawaan."""
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "contoh_transaksi.txt")
        baris = []
        with open(path, encoding="utf-8") as f:
            for b in f:
                if b.strip().startswith("---"):
                    break
                if b.strip():
                    baris.append(b.strip())
        if baris:
            return "\n".join(baris)
    except OSError:
        pass
    return CONTOH_BAWAAN


def _js(jurnal):
    return json.dumps(jurnal, sort_keys=True, default=str)


@st.cache_data(show_spinner=False)
def hitung_neraca(js):
    return ak.neraca_saldo(json.loads(js))


@st.cache_data(show_spinner=False)
def hitung_laporan(js):
    return ak.laporan_keuangan(json.loads(js))


@st.cache_data(show_spinner=False)
def buat_excel(js):
    return ak.ke_excel(json.loads(js))


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
    client = get_client()
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
    respons = get_client().chat.completions.create(
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
# STATE & AKUN PENGGUNA (demo/lokal, hanya di st.session_state)
# ---------------------------------------------------------------------------
def buat_akun(nama, password):
    garam = os.urandom(16)
    return {"nama": nama, "garam": garam, "hash": _hash(password, garam)}


def _hash(password, garam):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), garam, 100_000).hex()


def init_state():
    if "users" not in st.session_state:
        st.session_state.users = {"demo": buat_akun("Pengguna Demo", "demo123")}
    awal = {
        "user": None,            # {"username","nama","tamu"} saat sudah masuk
        "data": {},              # {username: {"jurnal": [...], "komentar": ""}}
        "menu": M_DASHBOARD,
        "draf": [],
        "draf_versi": 0,
        "pertanyaan": "",
        "input_terakhir": "",
        "tanggal_terakhir": date.today().isoformat(),
        "log": [],
        "pesan_sukses": "",
        "teks_input": "",
    }
    for k, v in awal.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if st.session_state.pop("kosongkan_input", False):
        st.session_state.teks_input = ""


def data_user():
    u = st.session_state.user["username"]
    return st.session_state.data.setdefault(u, {"jurnal": [], "komentar": ""})


def pindah(menu):
    st.session_state.menu = menu


def masuk(username, nama, tamu=False):
    st.session_state.user = {"username": username, "nama": nama, "tamu": tamu}
    st.session_state.menu = M_DASHBOARD


def masuk_tamu():
    masuk("tamu", "Tamu Uji Coba", tamu=True)


def keluar():
    """Logout: bersihkan sesi kerja. Data jurnal tiap akun tetap ada selama sesi browser."""
    st.session_state.user = None
    st.session_state.menu = M_DASHBOARD
    st.session_state.draf = []
    st.session_state.pertanyaan = ""
    st.session_state.input_terakhir = ""
    st.session_state.log = []
    st.session_state.pesan_sukses = ""
    st.session_state.teks_input = ""


def isi_contoh():
    st.session_state.teks_input = muat_contoh()


# ---------------------------------------------------------------------------
# HALAMAN: MASUK / DAFTAR
# ---------------------------------------------------------------------------
def halaman_masuk():
    _, tengah, _ = st.columns([1, 1.5, 1])
    with tengah:
        st.markdown(
            '<div class="hero"><h1>🌿 Akun Pintar</h1>'
            "<p>Ubah kalimat transaksi sehari-hari menjadi jurnal, buku besar, "
            "dan laporan keuangan.</p></div>",
            unsafe_allow_html=True,
        )
        tab_masuk, tab_daftar = st.tabs(["Masuk", "Daftar"])

        with tab_masuk:
            with st.form("form_masuk"):
                u = st.text_input("Nama pengguna")
                p = st.text_input("Kata sandi", type="password")
                kirim = st.form_submit_button("Masuk", type="primary")
            if kirim:
                akun = st.session_state.users.get(u.strip().lower())
                if akun and hmac.compare_digest(akun["hash"], _hash(p, akun["garam"])):
                    masuk(u.strip().lower(), akun["nama"])
                    st.rerun()
                else:
                    st.error("Nama pengguna atau kata sandi salah.")
            st.caption("Akun demo: nama pengguna `demo`, kata sandi `demo123`.")
            st.button("🚀 Masuk cepat tanpa daftar", on_click=masuk_tamu)

        with tab_daftar:
            with st.form("form_daftar"):
                nama = st.text_input("Nama lengkap")
                u2 = st.text_input("Nama pengguna", help="3–20 karakter: huruf kecil, angka, atau garis bawah.")
                p2 = st.text_input("Kata sandi", type="password", help="Minimal 6 karakter.")
                p3 = st.text_input("Ulangi kata sandi", type="password")
                daftar = st.form_submit_button("Daftar dan masuk", type="primary")
            if daftar:
                uname = u2.strip().lower()
                if not nama.strip():
                    st.error("Nama lengkap wajib diisi.")
                elif not re.fullmatch(r"[a-z0-9_]{3,20}", uname):
                    st.error("Nama pengguna harus 3–20 karakter: huruf kecil, angka, atau garis bawah.")
                elif uname in st.session_state.users or uname == "tamu":
                    st.error("Nama pengguna sudah dipakai. Coba yang lain.")
                elif len(p2) < 6:
                    st.error("Kata sandi minimal 6 karakter.")
                elif p2 != p3:
                    st.error("Kata sandi dan pengulangannya tidak sama.")
                else:
                    st.session_state.users[uname] = buat_akun(nama.strip(), p2)
                    masuk(uname, nama.strip())
                    st.rerun()

        st.caption(
            "Akun bersifat lokal untuk sesi ini (demo). Data hilang saat halaman dimuat ulang, "
            "jadi unduh Excel sebelum menutup aplikasi."
        )


# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
def sidebar():
    u = st.session_state.user
    with st.sidebar:
        st.markdown(
            '<div class="brand">🌿 Akun Pintar</div><div class="brand-sub">Jurnal otomatis dari kalimat biasa</div>',
            unsafe_allow_html=True,
        )
        nama = html.escape(u["nama"])
        sub = "Mode uji coba" if u["tamu"] else "@" + html.escape(u["username"])
        st.markdown(
            f'<div class="user-chip"><div class="avatar">{html.escape(u["nama"][:1].upper())}</div>'
            f"<div><b>{nama}</b><br><span>{sub}</span></div></div>",
            unsafe_allow_html=True,
        )
        for i, m in enumerate(MENU):
            st.button(
                m,
                key=f"nav_{i}",
                type="primary" if st.session_state.menu == m else "secondary",
                on_click=pindah,
                args=(m,),
            )
        st.divider()
        st.caption(f"Model AI: `{MODEL}`")
        with st.expander("📚 Daftar akun"):
            st.dataframe(daftar_akun(), hide_index=True)
        st.button("🚪 Keluar / ganti akun", on_click=keluar)


# ---------------------------------------------------------------------------
# KOMPONEN BERSAMA
# ---------------------------------------------------------------------------
def kosong(teks):
    st.markdown(
        f'<div class="kartu"><h4>Belum ada data</h4><p>{html.escape(teks)}</p></div>',
        unsafe_allow_html=True,
    )
    st.button("✍️ Input transaksi pertama", on_click=pindah, args=(M_INPUT,), type="primary", key=f"kosong_{st.session_state.menu}")


def grafik_laba_rugi(lap):
    df = pd.DataFrame({
        "Pos": ["Pendapatan", "Beban", "Laba (Rugi) Bersih"],
        "Jumlah": [lap["total_pendapatan"], lap["total_beban"], lap["laba_bersih"]],
    })
    fig = px.bar(
        df, x="Pos", y="Jumlah", color="Pos", text_auto=".3s", title="Ringkasan laba rugi",
        color_discrete_map={"Pendapatan": "#34d399", "Beban": "#9ca3af", "Laba (Rugi) Bersih": "#047857"},
    )
    fig.update_layout(
        showlegend=False, plot_bgcolor="white", paper_bgcolor="white",
        margin=dict(l=10, r=10, t=50, b=10), font=dict(color="#0f2a1d"),
    )
    fig.update_xaxes(title=None)
    fig.update_yaxes(gridcolor="#e3f4ea", title=None)
    return fig


def grafik_aset(lap):
    df = pd.DataFrame({"Akun": list(lap["aset"].keys()), "Saldo": list(lap["aset"].values())})
    df = df[df["Saldo"] > 0]
    if df.empty:
        return None
    fig = px.pie(df, names="Akun", values="Saldo", hole=0.55, title="Komposisi aset", color_discrete_sequence=HIJAU)
    fig.update_layout(paper_bgcolor="white", margin=dict(l=10, r=10, t=50, b=10), font=dict(color="#0f2a1d"))
    return fig


# ---------------------------------------------------------------------------
# HALAMAN 1: DASHBOARD
# ---------------------------------------------------------------------------
def halaman_dashboard(U):
    jurnal = U["jurnal"]
    nama = html.escape(st.session_state.user["nama"].split()[0])
    st.markdown(
        f'<div class="hero"><h1>Halo, {nama}</h1>'
        "<p>Ringkasan pembukuan Anda hari ini.</p></div>",
        unsafe_allow_html=True,
    )

    if not jurnal:
        kosong("Tulis transaksi dengan kalimat biasa, lalu AI menyusun jurnalnya.")
        return

    js = _js(jurnal)
    _, total_d, total_k, seimbang = hitung_neraca(js)
    lap = hitung_laporan(js)

    m1, m2, m3 = st.columns(3)
    m1.metric("Jumlah transaksi", len(jurnal))
    m2.metric("Total debit = kredit", ak.rp(total_d))
    m3.metric("Neraca saldo", "✅ Seimbang" if seimbang else "❌ Tidak seimbang")

    n1, n2, n3 = st.columns(3)
    n1.metric("Total aset", ak.rp(lap["total_aset"]))
    n2.metric("Laba (rugi) bersih", ak.rp(lap["laba_bersih"]))
    n3.metric("Ekuitas akhir", ak.rp(lap["ekuitas_akhir"]))

    b1, b2, b3, _ = st.columns([1.2, 1, 1.2, 2])
    b1.button("✍️ Input transaksi baru", on_click=pindah, args=(M_INPUT,), type="primary", key="d_input")
    b2.button("📒 Lihat jurnal", on_click=pindah, args=(M_JURNAL,), key="d_jurnal")
    b3.button("📑 Buka laporan", on_click=pindah, args=(M_LAP,), key="d_lap")

    kiri, kanan = st.columns([1.2, 1])
    with kiri:
        st.markdown("**Aktivitas terakhir**")
        tampil = ak.jurnal_tampil_df(jurnal[-5:])
        st.dataframe(
            tampil.style.format({"Debit": ak.fmt_kosong, "Kredit": ak.fmt_kosong}),
            hide_index=True,
        )
    with kanan:
        st.plotly_chart(grafik_laba_rugi(lap))


# ---------------------------------------------------------------------------
# HALAMAN 2: INPUT TRANSAKSI
# ---------------------------------------------------------------------------
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


def halaman_input(U):
    judul("✍️", "Input transaksi", "Tulis transaksi dengan kalimat biasa. AI menyusun draf, Python memeriksa debit = kredit.")

    ada_kunci = get_client() is not None
    if not ada_kunci:
        st.error("🚨 API Key belum diatur. Isi GROQ_API_KEY di Streamlit Secrets (atau file .env saat dijalankan lokal).")

    kiri, kanan = st.columns([3, 1])
    with kanan:
        tanggal_default = st.date_input("Tanggal (jika tidak disebut di kalimat)", value=date.today())
        st.button("📋 Isi contoh transaksi", on_click=isi_contoh)
    with kiri:
        teks = st.text_area(
            "Transaksi (satu per baris)",
            key="teks_input",
            height=180,
            placeholder="Contoh: Beli perlengkapan Rp500.000 tunai",
        )
        proses = st.button("🤖 Proses dengan AI", type="primary", disabled=not ada_kunci)

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
        st.subheader("📝 Tinjau draf jurnal")
        st.caption("Periksa akun dan nominalnya. Kamu boleh mengedit sebelum menyimpan.")

        hasil_edit = []
        for i, t in enumerate(st.session_state.draf):
            kunci = f"{st.session_state.draf_versi}_{i}"
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                ket = c1.text_input("Keterangan", value=t["keterangan"], key=f"ket_{kunci}")
                tgl = c2.date_input("Tanggal", value=date.fromisoformat(t["tanggal"]), key=f"tgl_{kunci}")
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
                    bersih["no"] = len(U["jurnal"]) + 1
                    U["jurnal"].append(bersih)
                st.session_state.draf = []
                st.session_state.input_terakhir = ""
                st.session_state.kosongkan_input = True
                U["komentar"] = ""
                st.session_state.pesan_sukses = f"✅ {len(baru)} transaksi disimpan ke Jurnal Umum."
                st.rerun()

        if b2.button("🗑️ Buang draf"):
            st.session_state.draf = []
            st.rerun()

    if st.session_state.log:
        with st.expander("🔍 Jejak kerja agent"):
            for baris_log in st.session_state.log:
                st.write(f"- {baris_log}")


# ---------------------------------------------------------------------------
# HALAMAN 3: JURNAL UMUM
# ---------------------------------------------------------------------------
def halaman_jurnal(U):
    judul("📒", "Jurnal umum", "Semua transaksi yang sudah disetujui, urut sesuai input.")
    jurnal = U["jurnal"]
    if not jurnal:
        kosong("Jurnal umum terisi setelah Anda menyimpan transaksi.")
        return

    tanggal = [date.fromisoformat(t["tanggal"]) for t in jurnal]
    tmin, tmax = min(tanggal), max(tanggal)

    with st.container(border=True):
        f1, f2, f3 = st.columns([1.3, 1.5, 1.2])
        rentang = f1.date_input("Rentang tanggal", value=(tmin, tmax), min_value=tmin, max_value=tmax)
        akun_pilih = f2.multiselect("Akun", ak.akun_terpakai(jurnal), placeholder="Semua akun")
        kata = f3.text_input("Cari keterangan")

    if isinstance(rentang, (tuple, list)):
        awal, akhir = (rentang[0], rentang[-1]) if len(rentang) else (tmin, tmax)
    else:
        awal = akhir = rentang

    tersaring = ak.filter_jurnal(jurnal, awal, akhir, akun_pilih, kata)
    df = ak.jurnal_ke_df(tersaring)

    s1, s2, s3 = st.columns(3)
    s1.metric("Transaksi ditampilkan", f"{len(tersaring)} dari {len(jurnal)}")
    s2.metric("Total debit", ak.rp(df["Debit"].sum()))
    s3.metric("Total kredit", ak.rp(df["Kredit"].sum()))

    if tersaring:
        tampil = ak.jurnal_tampil_df(tersaring)
        st.dataframe(
            tampil.style.format({"Debit": ak.fmt_kosong, "Kredit": ak.fmt_kosong}),
            hide_index=True,
        )
    else:
        st.info("Tidak ada transaksi yang cocok dengan filter.")

    with st.expander("⚙️ Kelola jurnal"):
        c1, c2, _ = st.columns([1.3, 1.2, 3])
        if c1.button("↩️ Hapus transaksi terakhir"):
            U["jurnal"].pop()
            U["komentar"] = ""
            st.rerun()
        if c2.button("🗑️ Hapus semua jurnal"):
            U["jurnal"].clear()
            U["komentar"] = ""
            st.rerun()


# ---------------------------------------------------------------------------
# HALAMAN 4: BUKU BESAR
# ---------------------------------------------------------------------------
def halaman_buku_besar(U):
    judul("📚", "Buku besar", "Mutasi dan saldo berjalan untuk setiap akun.")
    jurnal = U["jurnal"]
    if not jurnal:
        kosong("Buku besar terbentuk otomatis setelah ada transaksi.")
        return

    akun_pilih = st.selectbox("Pilih akun", ak.akun_terpakai(jurnal))
    df_bb, saldo_akhir = ak.buku_besar(jurnal, akun_pilih)
    kategori, normal = ak.AKUN[akun_pilih]

    c1, c2, c3 = st.columns(3)
    c1.metric(f"Saldo akhir {akun_pilih}", ak.rp(saldo_akhir))
    c2.metric("Total debit", ak.rp(df_bb["Debit"].sum()))
    c3.metric("Total kredit", ak.rp(df_bb["Kredit"].sum()))
    st.caption(f"Kategori: {kategori} · Saldo normal: {normal}")

    st.dataframe(
        df_bb.style.format({"Debit": ak.fmt_kosong, "Kredit": ak.fmt_kosong, "Saldo": ak.fmt_angka}),
        hide_index=True,
    )

    with st.expander("Saldo semua akun"):
        ringkas = pd.DataFrame([
            {"Akun": a, "Kategori": ak.AKUN[a][0], "Saldo (Rp)": ak.fmt_angka(s)}
            for a, s in ak.saldo_semua_akun(jurnal).items()
        ])
        st.dataframe(ringkas, hide_index=True)


# ---------------------------------------------------------------------------
# HALAMAN 5: NERACA SALDO
# ---------------------------------------------------------------------------
def halaman_neraca(U):
    judul("⚖️", "Neraca saldo", "Saldo akhir tiap akun di sisi debit atau kredit.")
    jurnal = U["jurnal"]
    if not jurnal:
        kosong("Neraca saldo terbentuk otomatis setelah ada transaksi.")
        return

    ns, total_d, total_k, seimbang = hitung_neraca(_js(jurnal))
    if seimbang:
        st.success(f"✅ Seimbang: total debit {ak.rp(total_d)} = total kredit {ak.rp(total_k)}")
    else:
        st.error(f"❌ Tidak seimbang: debit {ak.rp(total_d)} ≠ kredit {ak.rp(total_k)}")

    ns_tampil = pd.concat(
        [ns, pd.DataFrame([{"Akun": "TOTAL", "Debit": total_d, "Kredit": total_k}])],
        ignore_index=True,
    )
    st.dataframe(
        ns_tampil.style.format({"Debit": ak.fmt_kosong, "Kredit": ak.fmt_kosong}),
        hide_index=True,
    )


# ---------------------------------------------------------------------------
# HALAMAN 6: LAPORAN KEUANGAN
# ---------------------------------------------------------------------------
def halaman_laporan(U):
    judul("📑", "Laporan keuangan", "Laba rugi dan posisi keuangan sederhana, dihitung Python dari jurnal.")
    jurnal = U["jurnal"]
    if not jurnal:
        kosong("Laporan keuangan terbentuk otomatis setelah ada transaksi.")
        return

    lap = hitung_laporan(_js(jurnal))

    x1, x2, x3 = st.columns(3)
    x1.metric("Total pendapatan", ak.rp(lap["total_pendapatan"]))
    x2.metric("Total beban", ak.rp(lap["total_beban"]))
    x3.metric("Laba (rugi) bersih", ak.rp(lap["laba_bersih"]))

    kiri, kanan = st.columns(2)
    with kiri:
        st.markdown("**Laporan laba rugi**")
        st.dataframe(ak.tabel_laporan(ak.baris_laba_rugi(lap)), hide_index=True)
    with kanan:
        st.markdown("**Laporan posisi keuangan (neraca)**")
        st.dataframe(ak.tabel_laporan(ak.baris_posisi_keuangan(lap)), hide_index=True)

    if lap["seimbang"]:
        st.success("✅ Persamaan akuntansi seimbang: Aset = Liabilitas + Ekuitas")
    else:
        st.error("❌ Persamaan akuntansi tidak seimbang. Periksa jurnal.")

    g1, g2 = st.columns(2)
    g1.plotly_chart(grafik_laba_rugi(lap))
    fig_aset = grafik_aset(lap)
    if fig_aset is not None:
        g2.plotly_chart(fig_aset)

    st.markdown("### 🤖 Komentar AI")
    if st.button("Buat komentar AI", disabled=get_client() is None):
        with st.spinner("AI sedang menulis komentar..."):
            try:
                U["komentar"] = buat_komentar(jurnal)
            except Exception as e:
                st.error(f"Gagal menghubungi AI: {e}")
    if U["komentar"]:
        st.write(U["komentar"])
        st.caption("Komentar ini ditulis AI dari angka yang dihitung Python. Tetap periksa kembali.")


# ---------------------------------------------------------------------------
# HALAMAN 7: EKSPOR
# ---------------------------------------------------------------------------
def halaman_ekspor(U):
    judul("📥", "Ekspor Excel", "Unduh seluruh hasil pembukuan dalam satu file.")
    jurnal = U["jurnal"]
    if not jurnal:
        kosong("Belum ada data untuk diunduh.")
        return

    st.write("File Excel berisi lima lembar: Jurnal Umum, Buku Besar, Neraca Saldo, Laba Rugi, dan Posisi Keuangan.")
    st.download_button(
        "📥 Unduh Excel",
        data=buat_excel(_js(jurnal)),
        file_name=f"akunpintar_{st.session_state.user['username']}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )
    st.caption("Data hanya tersimpan selama aplikasi dibuka. Unduh dulu sebelum menutup halaman.")


# ---------------------------------------------------------------------------
# PROGRAM UTAMA
# ---------------------------------------------------------------------------
HALAMAN = {
    M_DASHBOARD: halaman_dashboard,
    M_INPUT: halaman_input,
    M_JURNAL: halaman_jurnal,
    M_BB: halaman_buku_besar,
    M_NS: halaman_neraca,
    M_LAP: halaman_laporan,
    M_EKSPOR: halaman_ekspor,
}

pasang_css()
init_state()

if not st.session_state.user:
    halaman_masuk()
    st.stop()

sidebar()

if st.session_state.pesan_sukses:
    st.success(st.session_state.pesan_sukses)
    st.session_state.pesan_sukses = ""

HALAMAN[st.session_state.menu](data_user())
