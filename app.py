"""
Akun Pintar - Asisten Jurnal Otomatis dari Kalimat Biasa
=========================================================
Alur:
    Masuk/Daftar -> Input transaksi -> AI menyusun draf jurnal -> Python memvalidasi
    (debit = kredit) -> pengguna meninjau -> Jurnal Umum -> Buku Besar -> Neraca Saldo
    -> Laporan Keuangan -> Ekspor / Cadangan

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
from datetime import date, datetime

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
    "🗂️ Kelola Akun",
    "💾 Cadangan & Ekspor",
]
M_DASHBOARD, M_INPUT, M_JURNAL, M_BB, M_NS, M_LAP, M_AKUN, M_CADANGAN = MENU

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
.cek{display:flex;gap:.6rem;align-items:flex-start;padding:.6rem .85rem;margin-bottom:.4rem;background:#fff;
  border:1px solid var(--garis);border-left:4px solid var(--hijau);border-radius:10px;font-size:.93rem;}
.cek.warn{border-left-color:#d97706;background:#fffbeb;border-color:#fde68a;}
.cek.bad{border-left-color:#dc2626;background:#fef2f2;border-color:#fecaca;}
.cek.info{border-left-color:#6b7f74;}
</style>
"""


def pasang_css():
    st.markdown(CSS, unsafe_allow_html=True)


def judul(ikon, teks, sub=""):
    st.markdown(
        f'<div class="judul"><h2>{ikon} {html.escape(teks)}</h2><p>{html.escape(sub)}</p></div>',
        unsafe_allow_html=True,
    )


def kartu_cek(level, teks):
    """Satu baris hasil pemeriksaan. level: ok | warn | bad | info."""
    ikon = {"ok": "✅", "warn": "⚠️", "bad": "❌", "info": "ℹ️"}[level]
    st.markdown(
        f'<div class="cek {level}"><span>{ikon}</span><span>{html.escape(teks)}</span></div>',
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
# PROMPT UNTUK AI (daftar akun kini mengikuti COA pengguna)
# ---------------------------------------------------------------------------
PROMPT_TEMPLATE = """Kamu adalah asisten akuntansi yang mengubah kalimat transaksi menjadi jurnal umum (double-entry).

DAFTAR AKUN (format: kode nama akun (kategori, saldo normal)). Tulis HANYA nama akunnya, tanpa kode, persis sama penulisannya:
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
9. JANGAN membuat akun baru. Jika tidak ada akun di daftar yang cocok, jawab dengan status "tanya".
10. Jawab HANYA dengan JSON, tanpa teks lain dan tanpa markdown.

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
# DATA STATIS & HITUNGAN (di-cache; kunci cache = JSON jurnal + JSON daftar akun)
# ---------------------------------------------------------------------------
def _js(obj):
    return json.dumps(obj, sort_keys=True, default=str)


def _peta(cjs):
    return ak.coa_ke_peta(json.loads(cjs))


@st.cache_data
def buat_prompt_sistem(cjs):
    daftar = "\n".join(
        f"- {a['kode']} {a['nama']} ({a['kategori']}, saldo normal {a['normal']})"
        for a in ak.urutkan_coa(json.loads(cjs))
    )
    return PROMPT_TEMPLATE.replace("{{DAFTAR_AKUN}}", daftar)


@st.cache_data
def tabel_coa(cjs):
    return ak.daftar_akun_df(json.loads(cjs))


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


@st.cache_data(show_spinner=False)
def hitung_neraca(js, cjs):
    return ak.neraca_saldo(json.loads(js), _peta(cjs))


@st.cache_data(show_spinner=False)
def hitung_laporan(js, cjs):
    return ak.laporan_keuangan(json.loads(js), _peta(cjs))


@st.cache_data(show_spinner=False)
def hitung_pemeriksaan(js, cjs):
    return ak.pemeriksaan_keseimbangan(json.loads(js), _peta(cjs))


@st.cache_data(show_spinner=False)
def buat_excel(js, cjs):
    return ak.ke_excel(json.loads(js), _peta(cjs))


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


def jalankan_agent(teks, tanggal_default, cjs, maks_ulang=2):
    """
    Return: (hasil, log)
        hasil["status"] = "ok"    -> hasil["transaksi"] berisi draf jurnal valid
                        = "tanya" -> hasil["pertanyaan"] berisi pertanyaan agent
                        = "gagal" -> hasil["pesan"] berisi penyebab
    """
    client = get_client()
    peta = _peta(cjs)
    log = []
    pesan = [
        {"role": "system", "content": buat_prompt_sistem(cjs)},
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
                bersih, error = ak.periksa_transaksi(t, peta)
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


def buat_komentar(U):
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
            {"role": "user", "content": ak.ringkasan_untuk_ai(U["jurnal"], ak.coa_ke_peta(U["coa"]))},
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
        "data": {},              # {username: data pengguna, lihat data_baru()}
        "menu": M_DASHBOARD,
        "draf": [],
        "draf_versi": 0,
        "pertanyaan": "",
        "input_terakhir": "",
        "tanggal_terakhir": date.today().isoformat(),
        "log": [],
        "pesan_sukses": "",
        "teks_input": "",
        "tgl_input": date.today(),
        "hapus_menunggu": None,
        "upload_n": 0,
    }
    for k, v in awal.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # Supaya isi kotak input tidak hilang saat pindah menu: Streamlit membuang state widget
    # yang tidak ditampilkan; menyalin ulang nilainya setiap run mencegah pembersihan itu.
    for k in ("teks_input", "tgl_input"):
        st.session_state[k] = st.session_state[k]

    if st.session_state.pop("kosongkan_input", False):
        st.session_state.teks_input = ""


def data_baru():
    return {"jurnal": [], "coa": ak.coa_default(), "komentar": "", "versi": 0, "versi_cadangan": 0}


def data_user():
    u = st.session_state.user["username"]
    if u not in st.session_state.data:
        st.session_state.data[u] = data_baru()
    return st.session_state.data[u]


def ubah_data(U):
    """Tandai data berubah (dipakai penanda cadangan & kunci widget); komentar AI jadi usang."""
    U["versi"] += 1
    U["komentar"] = ""


def snap(U):
    """(JSON jurnal, JSON daftar akun) sebagai kunci cache."""
    return _js(U["jurnal"]), _js(U["coa"])


def tandai_cadangan():
    U = data_user()
    U["versi_cadangan"] = U["versi"]


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
    st.session_state.hapus_menunggu = None


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
            "jadi unduh cadangan di menu Cadangan & Ekspor sebelum menutup aplikasi."
        )


# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
def sidebar(U):
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

        # Status draf & cadangan
        if st.session_state.draf:
            st.caption(f"📝 {len(st.session_state.draf)} draf jurnal menunggu persetujuan (menu Input Transaksi).")
        elif st.session_state.pertanyaan:
            st.caption("🤔 Agent menunggu jawabanmu (menu Input Transaksi).")
        if U["jurnal"]:
            if U["versi"] != U["versi_cadangan"]:
                st.caption("⚠️ Ada perubahan yang belum dicadangkan.")
            else:
                st.caption("✅ Data sudah dicadangkan.")

        st.divider()
        st.caption(f"Model AI: `{MODEL}`")
        with st.expander("📚 Daftar akun"):
            st.dataframe(tabel_coa(_js(U["coa"])), hide_index=True)
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


def daftar_cek(cek):
    """Hasil pemeriksaan -> list (level, teks) siap ditampilkan."""
    item = []
    if cek["transaksi_tidak_seimbang"]:
        nomor = ", ".join(str(n) for n in cek["transaksi_tidak_seimbang"])
        item.append(("bad", f"Transaksi tidak seimbang: no. {nomor}. Edit transaksi tersebut di Jurnal Umum."))
    else:
        item.append(("ok", "Setiap transaksi seimbang (debit = kredit)."))
    if cek["total_debit"] == cek["total_kredit"]:
        item.append(("ok", f"Neraca saldo seimbang: total debit {ak.rp(cek['total_debit'])} = total kredit {ak.rp(cek['total_kredit'])}."))
    else:
        item.append(("bad", f"Neraca saldo tidak seimbang: debit {ak.rp(cek['total_debit'])} ≠ kredit {ak.rp(cek['total_kredit'])}."))
    if cek["persamaan_seimbang"]:
        item.append(("ok", "Persamaan akuntansi seimbang: Aset = Liabilitas + Ekuitas."))
    else:
        item.append(("bad", f"Persamaan akuntansi tidak seimbang (selisih {ak.rp(abs(cek['selisih_persamaan']))}). Periksa kategori dan saldo normal akun."))
    for r in cek["indikator"]:
        if r["perhatian"]:
            item.append(("warn", f"{r['akun']} ({ak.rp(r['saldo'])}): {r['catatan']}"))
    for teks in cek["info"]:
        item.append(("info", teks))
    return item


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
        kosong("Tulis transaksi dengan kalimat biasa, lalu AI menyusun jurnalnya. Punya file cadangan? Muat di menu Cadangan & Ekspor.")
        return

    js, cjs = snap(U)
    _, total_d, total_k, seimbang = hitung_neraca(js, cjs)
    lap = hitung_laporan(js, cjs)
    cek = hitung_pemeriksaan(js, cjs)

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

    # Kesehatan pembukuan (ringkas)
    masalah = [(lv, tx) for lv, tx in daftar_cek(cek) if lv in ("bad", "warn")]
    st.markdown("**Kesehatan pembukuan**")
    if masalah:
        for lv, tx in masalah[:4]:
            kartu_cek(lv, tx)
        st.button("🩺 Lihat pemeriksaan lengkap", on_click=pindah, args=(M_NS,), key="d_cek")
    else:
        kartu_cek("ok", "Pembukuan sehat: semua pemeriksaan keseimbangan lolos dan tidak ada saldo akun yang janggal.")

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
def proses_teks(teks, tanggal_default, U):
    """Panggil agent lalu simpan hasilnya di state. Return status."""
    with st.spinner("🤖 AI sedang menyusun jurnal..."):
        try:
            hasil, log = jalankan_agent(teks, tanggal_default, _js(U["coa"]))
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


def df_dari_baris(baris):
    df = pd.DataFrame(
        [{"Akun": b.get("akun"), "Posisi": b.get("posisi"), "Nominal": b.get("nominal")} for b in baris],
        columns=["Akun", "Posisi", "Nominal"],
    )
    df["Nominal"] = pd.to_numeric(df["Nominal"], errors="coerce")
    return df


def baris_dari_df(df):
    """DataFrame editor -> list baris (nilai kosong jadi None; baris yang benar-benar kosong dibuang)."""
    hasil = []
    for _, r in df.iterrows():
        akun = None if pd.isna(r["Akun"]) else r["Akun"]
        posisi = None if pd.isna(r["Posisi"]) else r["Posisi"]
        nominal = None
        if not pd.isna(r["Nominal"]):
            nominal = int(r["Nominal"]) if float(r["Nominal"]).is_integer() else float(r["Nominal"])
        if akun is None and posisi is None and nominal is None:
            continue
        hasil.append({"akun": akun, "posisi": posisi, "nominal": nominal})
    return hasil


def baris_siap_simpan(df):
    """Hanya baris yang akun dan nominalnya terisi (sama seperti perilaku sebelumnya)."""
    return [
        {"akun": b["akun"], "posisi": b["posisi"] or "", "nominal": b["nominal"]}
        for b in baris_dari_df(df)
        if b["akun"] is not None and b["nominal"] is not None
    ]


def konfigurasi_editor(peta):
    return {
        "Akun": st.column_config.SelectboxColumn("Akun", options=list(peta.keys()), required=True),
        "Posisi": st.column_config.SelectboxColumn("Posisi", options=["debit", "kredit"], required=True),
        "Nominal": st.column_config.NumberColumn("Nominal (Rp)", min_value=0, step=1000, format="%d"),
    }


def indikator_seimbang(df_edit):
    d = df_edit.loc[df_edit["Posisi"] == "debit", "Nominal"].sum()
    k = df_edit.loc[df_edit["Posisi"] == "kredit", "Nominal"].sum()
    if d == k and d > 0:
        st.success(f"✅ Seimbang: debit {ak.rp(d)} = kredit {ak.rp(k)}")
    else:
        st.error(f"❌ Belum seimbang: debit {ak.rp(d)} ≠ kredit {ak.rp(k)}")


def halaman_input(U):
    judul("✍️", "Input transaksi", "Tulis transaksi dengan kalimat biasa. AI menyusun draf, Python memeriksa debit = kredit.")
    peta = ak.coa_ke_peta(U["coa"])

    ada_kunci = get_client() is not None
    if not ada_kunci:
        st.error("🚨 API Key belum diatur. Isi GROQ_API_KEY di Streamlit Secrets (atau file .env saat dijalankan lokal).")

    kiri, kanan = st.columns([3, 1])
    with kanan:
        st.date_input("Tanggal (jika tidak disebut di kalimat)", key="tgl_input")
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
            proses_teks(teks.strip(), st.session_state.tgl_input.isoformat(), U)

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
            status = proses_teks(gabungan, st.session_state.tanggal_terakhir, U)
            if status != "gagal":
                st.rerun()

    # --- Tinjau draf (human-in-the-loop). Edit disalin balik ke st.session_state.draf di
    #     setiap run, dan editor dipasang ulang dari salinan itu setelah pindah menu.
    if st.session_state.draf:
        st.subheader("📝 Tinjau draf jurnal")
        st.caption("Periksa akun dan nominalnya. Perubahanmu tetap tersimpan walau kamu pindah menu.")

        hasil_edit = []
        for i, t in enumerate(st.session_state.draf):
            kunci = f"{st.session_state.draf_versi}_{i}"
            k_ket, k_tgl, k_ed, k_beku = f"ket_{kunci}", f"tgl_{kunci}", f"edit_{kunci}", f"beku_{kunci}"
            if k_beku not in st.session_state or k_ket not in st.session_state:
                # editor baru dipasang (draf baru atau kembali dari menu lain): mulai dari draf terakhir
                st.session_state[k_beku] = {
                    "ket": t["keterangan"],
                    "tgl": date.fromisoformat(t["tanggal"]),
                    "df": df_dari_baris(t["baris"]),
                }
            beku = st.session_state[k_beku]
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                ket = c1.text_input("Keterangan", value=beku["ket"], key=k_ket)
                tgl = c2.date_input("Tanggal", value=beku["tgl"], key=k_tgl)
                df_edit = st.data_editor(
                    beku["df"],
                    key=k_ed,
                    num_rows="dynamic",
                    hide_index=True,
                    column_config=konfigurasi_editor(peta),
                )
                indikator_seimbang(df_edit)
            st.session_state.draf[i] = {
                "keterangan": ket,
                "tanggal": tgl.isoformat(),
                "baris": baris_dari_df(df_edit),
            }
            hasil_edit.append((ket, tgl, df_edit))

        b1, b2, _ = st.columns([1.2, 1, 3])
        if b1.button("✅ Setuju & simpan", type="primary"):
            baru, semua_error = [], []
            for no, (ket, tgl, df_edit) in enumerate(hasil_edit, start=1):
                bersih, error = ak.periksa_transaksi(
                    {"tanggal": tgl.isoformat(), "keterangan": ket, "baris": baris_siap_simpan(df_edit)}, peta
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
                ubah_data(U)
                st.session_state.draf = []
                st.session_state.input_terakhir = ""
                st.session_state.kosongkan_input = True
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
# HALAMAN 3: JURNAL UMUM (filter, cari, edit, hapus)
# ---------------------------------------------------------------------------
def bagian_edit_transaksi(U, tersaring, peta):
    jurnal = U["jurnal"]
    st.markdown("### ✏️ Edit atau hapus transaksi")
    if not tersaring:
        st.caption("Tidak ada transaksi pada hasil filter untuk diedit.")
        return

    ids = {id(t) for t in tersaring}
    opsi = {
        f'No. {t["no"]} · {t["tanggal"]} · {t["keterangan"]}': i
        for i, t in enumerate(jurnal) if id(t) in ids
    }
    pilih = st.selectbox("Pilih transaksi", list(opsi.keys()))
    i = opsi[pilih]
    t = jurnal[i]
    kunci = f'{U["versi"]}_{t["no"]}'

    with st.container(border=True):
        c1, c2 = st.columns([3, 1])
        ket = c1.text_input("Keterangan", value=t["keterangan"], key=f"eket_{kunci}")
        tgl = c2.date_input("Tanggal", value=date.fromisoformat(t["tanggal"]), key=f"etgl_{kunci}")
        df_edit = st.data_editor(
            df_dari_baris([{"akun": b["akun"], "posisi": b["posisi"], "nominal": b["nominal"]} for b in t["baris"]]),
            key=f"eed_{kunci}",
            num_rows="dynamic",
            hide_index=True,
            column_config=konfigurasi_editor(peta),
        )
        indikator_seimbang(df_edit)

        b1, b2, _ = st.columns([1.2, 1.2, 3])
        if b1.button("💾 Simpan perubahan", type="primary", key=f"simpan_{kunci}"):
            bersih, error = ak.periksa_transaksi(
                {"tanggal": tgl.isoformat(), "keterangan": ket, "baris": baris_siap_simpan(df_edit)}, peta
            )
            if error:
                st.error("Belum bisa disimpan:\n\n" + "\n".join(f"- {e}" for e in error))
            else:
                bersih["no"] = t["no"]
                U["jurnal"][i] = bersih
                ubah_data(U)
                st.session_state.pesan_sukses = (
                    f"✅ Transaksi no. {t['no']} diperbarui. Buku besar, neraca saldo, dan laporan ikut terbarui."
                )
                st.rerun()
        if b2.button("🗑️ Hapus transaksi", key=f"hapus_{kunci}"):
            st.session_state.hapus_menunggu = t["no"]

    if st.session_state.hapus_menunggu == t["no"]:
        st.warning(f"Hapus transaksi no. {t['no']} ({t['keterangan']})? Nomor transaksi sesudahnya akan bergeser.")
        y, n, _ = st.columns([1, 1, 4])
        if y.button("Ya, hapus", type="primary", key=f"ya_{kunci}"):
            U["jurnal"].pop(i)
            ak.nomori_ulang(U["jurnal"])
            ubah_data(U)
            st.session_state.hapus_menunggu = None
            st.session_state.pesan_sukses = "🗑️ Transaksi dihapus. Buku besar, neraca saldo, dan laporan ikut terbarui."
            st.rerun()
        if n.button("Batal", key=f"batal_{kunci}"):
            st.session_state.hapus_menunggu = None
            st.rerun()


def halaman_jurnal(U):
    judul("📒", "Jurnal umum", "Semua transaksi yang sudah disetujui. Cari, edit, atau hapus di sini.")
    jurnal = U["jurnal"]
    if not jurnal:
        kosong("Jurnal umum terisi setelah Anda menyimpan transaksi.")
        return
    peta = ak.coa_ke_peta(U["coa"])

    tanggal = [date.fromisoformat(t["tanggal"]) for t in jurnal]
    tmin, tmax = min(tanggal), max(tanggal)

    with st.container(border=True):
        f1, f2, f3 = st.columns([1.3, 1.5, 1.2])
        rentang = f1.date_input("Rentang tanggal", value=(tmin, tmax), min_value=tmin, max_value=tmax)
        akun_pilih = f2.multiselect("Akun", ak.akun_terpakai(jurnal, peta), placeholder="Semua akun")
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

    bagian_edit_transaksi(U, tersaring, peta)

    with st.expander("⚙️ Hapus banyak sekaligus"):
        c1, c2 = st.columns([1.3, 3])
        if c1.button("↩️ Hapus transaksi terakhir"):
            U["jurnal"].pop()
            ubah_data(U)
            st.rerun()
        yakin = st.checkbox("Saya yakin ingin menghapus SEMUA jurnal")
        if st.button("🗑️ Hapus semua jurnal", disabled=not yakin):
            U["jurnal"].clear()
            ubah_data(U)
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
    peta = ak.coa_ke_peta(U["coa"])
    kode = {a["nama"]: a["kode"] for a in U["coa"]}

    akun_pilih = st.selectbox(
        "Pilih akun", ak.akun_terpakai(jurnal, peta), format_func=lambda a: f"{kode.get(a, '')} · {a}"
    )
    df_bb, saldo_akhir = ak.buku_besar(jurnal, akun_pilih, peta)
    kategori, normal = peta[akun_pilih]

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
            {"Kode": kode.get(a, ""), "Akun": a, "Kategori": peta[a][0], "Saldo (Rp)": ak.fmt_angka(s)}
            for a, s in ak.saldo_semua_akun(jurnal, peta).items()
        ])
        st.dataframe(ringkas, hide_index=True)


# ---------------------------------------------------------------------------
# HALAMAN 5: NERACA SALDO + PEMERIKSAAN KESEIMBANGAN
# ---------------------------------------------------------------------------
def halaman_neraca(U):
    judul("⚖️", "Neraca saldo", "Saldo akhir tiap akun, lengkap dengan pemeriksaan keseimbangan.")
    jurnal = U["jurnal"]
    if not jurnal:
        kosong("Neraca saldo terbentuk otomatis setelah ada transaksi.")
        return

    js, cjs = snap(U)
    ns, total_d, total_k, seimbang = hitung_neraca(js, cjs)
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

    st.markdown("### 🩺 Pemeriksaan keseimbangan")
    cek = hitung_pemeriksaan(js, cjs)
    x1, x2, x3 = st.columns(3)
    x1.metric("Total debit", ak.rp(cek["total_debit"]))
    x2.metric("Total kredit", ak.rp(cek["total_kredit"]))
    x3.metric("Selisih", ak.rp(abs(cek["total_debit"] - cek["total_kredit"])))

    for level, teks in daftar_cek(cek):
        kartu_cek(level, teks)

    st.markdown("**Indikator akun**")
    tabel = pd.DataFrame([
        {
            "Akun": r["akun"],
            "Kategori": r["kategori"],
            "Saldo normal": r["normal"].capitalize(),
            "Saldo (Rp)": ak.fmt_angka(r["saldo"]),
            "Status": "⚠️ Perlu perhatian" if r["perhatian"] else "✅ Wajar",
            "Catatan": r["catatan"],
        }
        for r in cek["indikator"]
    ])
    st.dataframe(tabel, hide_index=True)


# ---------------------------------------------------------------------------
# HALAMAN 6: LAPORAN KEUANGAN
# ---------------------------------------------------------------------------
def halaman_laporan(U):
    judul("📑", "Laporan keuangan", "Laba rugi dan posisi keuangan sederhana, dihitung Python dari jurnal.")
    jurnal = U["jurnal"]
    if not jurnal:
        kosong("Laporan keuangan terbentuk otomatis setelah ada transaksi.")
        return

    js, cjs = snap(U)
    lap = hitung_laporan(js, cjs)

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
        st.error("❌ Persamaan akuntansi tidak seimbang. Periksa jurnal dan daftar akun.")

    g1, g2 = st.columns(2)
    g1.plotly_chart(grafik_laba_rugi(lap))
    fig_aset = grafik_aset(lap)
    if fig_aset is not None:
        g2.plotly_chart(fig_aset)

    st.markdown("### 🤖 Komentar AI")
    if st.button("Buat komentar AI", disabled=get_client() is None):
        with st.spinner("AI sedang menulis komentar..."):
            try:
                U["komentar"] = buat_komentar(U)
            except Exception as e:
                st.error(f"Gagal menghubungi AI: {e}")
    if U["komentar"]:
        st.write(U["komentar"])
        st.caption("Komentar ini ditulis AI dari angka yang dihitung Python. Tetap periksa kembali.")


# ---------------------------------------------------------------------------
# HALAMAN 7: KELOLA AKUN (COA)
# ---------------------------------------------------------------------------
def halaman_akun(U):
    judul("🗂️", "Kelola daftar akun", "Tambah atau sesuaikan akun. Daftar ini dipakai AI dan jurnal agar pencatatan konsisten.")
    jurnal, daftar = U["jurnal"], U["coa"]
    pakai = ak.jumlah_pemakaian(jurnal)

    a1, a2, a3 = st.columns(3)
    a1.metric("Jumlah akun", len(daftar))
    a2.metric("Akun terpakai di jurnal", len(pakai))
    a3.metric("Akun inti (terkunci)", len(ak.AKUN_INTI))

    tabel = pd.DataFrame([
        {
            "Kode": a["kode"],
            "Akun": a["nama"],
            "Kategori": a["kategori"],
            "Saldo normal": a["normal"].capitalize(),
            "Status": "🔒 Akun inti" if a["nama"] in ak.AKUN_INTI
            else (f"Dipakai di {pakai[a['nama']]} transaksi" if a["nama"] in pakai else "Belum dipakai"),
        }
        for a in ak.urutkan_coa(daftar)
    ])
    st.dataframe(tabel, hide_index=True)
    st.caption(
        "Akun inti dirujuk oleh aturan AI dan laporan, jadi hanya kodenya yang bisa diubah. "
        "Saran kode: Aset 1xx · Liabilitas 2xx · Ekuitas 3xx · Pendapatan 4xx · Beban 5xx."
    )

    tab_tambah, tab_ubah, tab_hapus = st.tabs(["➕ Tambah akun", "✏️ Ubah akun", "🗑️ Hapus akun"])

    with tab_tambah:
        with st.form("form_tambah_akun", clear_on_submit=True):
            c1, c2 = st.columns([1, 2])
            kode = c1.text_input("Kode akun", placeholder="mis. 106")
            nama = c2.text_input("Nama akun", placeholder="mis. Piutang Karyawan")
            c3, c4 = st.columns(2)
            kategori = c3.selectbox("Kategori", ak.URUTAN_KATEGORI)
            normal = c4.selectbox("Saldo normal", ["debit", "kredit"])
            kirim = st.form_submit_button("Tambah akun", type="primary")
        st.caption(
            "Aset & Beban biasanya bersaldo normal debit; Liabilitas, Ekuitas & Pendapatan biasanya kredit. "
            "Pilih sisi berlawanan hanya untuk akun pengurang (mis. Akumulasi Penyusutan)."
        )
        if kirim:
            error = ak.coa_tambah(daftar, kode, nama, kategori, normal)
            if error:
                st.error("\n\n".join(error))
            else:
                ubah_data(U)
                catatan = ""
                if normal != ak.NORMAL_KATEGORI[kategori]:
                    catatan = " Akun ini diperlakukan sebagai akun pengurang di kategorinya."
                st.session_state.pesan_sukses = f"✅ Akun '{nama.strip()}' ditambahkan.{catatan}"
                st.rerun()

    with tab_ubah:
        urut = ak.urutkan_coa(daftar)
        nama_pilih = st.selectbox("Pilih akun", [a["nama"] for a in urut], key="ubah_pilih")
        akun = next(a for a in urut if a["nama"] == nama_pilih)
        inti = nama_pilih in ak.AKUN_INTI
        if inti:
            st.info("Akun inti: hanya kode yang bisa diubah.")
        kf = f"{nama_pilih}_{U['versi']}"
        with st.form(f"form_ubah_{kf}"):
            c1, c2 = st.columns([1, 2])
            kode = c1.text_input("Kode akun", value=akun["kode"], key=f"uk_{kf}")
            nama = c2.text_input("Nama akun", value=akun["nama"], disabled=inti, key=f"un_{kf}")
            c3, c4 = st.columns(2)
            kategori = c3.selectbox(
                "Kategori", ak.URUTAN_KATEGORI, index=ak.URUTAN_KATEGORI.index(akun["kategori"]),
                disabled=inti, key=f"ukat_{kf}",
            )
            normal = c4.selectbox(
                "Saldo normal", ["debit", "kredit"], index=["debit", "kredit"].index(akun["normal"]),
                disabled=inti, key=f"unor_{kf}",
            )
            kirim = st.form_submit_button("Simpan perubahan", type="primary")
        if pakai.get(nama_pilih):
            st.caption(f"Akun ini dipakai di {pakai[nama_pilih]} transaksi. Jika namanya diubah, jurnal ikut diperbarui.")
        if kirim:
            error = ak.coa_ubah(daftar, nama_pilih, kode, nama, kategori, normal, jurnal)
            if error:
                st.error("\n\n".join(error))
            else:
                ubah_data(U)
                st.session_state.pesan_sukses = f"✅ Akun '{nama_pilih}' diperbarui. Laporan ikut terbarui."
                st.rerun()

    with tab_hapus:
        kandidat = [a["nama"] for a in ak.urutkan_coa(daftar) if a["nama"] not in ak.AKUN_INTI and not pakai.get(a["nama"])]
        if not kandidat:
            st.info("Tidak ada akun yang bisa dihapus. Akun inti dan akun yang sudah dipakai di jurnal tidak bisa dihapus.")
        else:
            hapus = st.selectbox("Akun yang dihapus", kandidat, key="hapus_pilih")
            if st.button("🗑️ Hapus akun"):
                error = ak.coa_hapus(daftar, hapus, jurnal)
                if error:
                    st.error("\n\n".join(error))
                else:
                    ubah_data(U)
                    st.session_state.pesan_sukses = f"🗑️ Akun '{hapus}' dihapus."
                    st.rerun()
        with st.expander("Kembalikan ke daftar akun bawaan"):
            st.write("Daftar akun diganti dengan bawaan aplikasi. Hanya bisa jika semua akun di jurnal ada di daftar bawaan.")
            yakin = st.checkbox("Saya yakin", key="yakin_reset_coa")
            if st.button("↩️ Kembalikan daftar bawaan", disabled=not yakin):
                error = ak.coa_kembalikan(daftar, jurnal)
                if error:
                    st.error("\n\n".join(error))
                else:
                    ubah_data(U)
                    st.session_state.pesan_sukses = "↩️ Daftar akun dikembalikan ke bawaan."
                    st.rerun()


# ---------------------------------------------------------------------------
# HALAMAN 8: CADANGAN & EKSPOR
# ---------------------------------------------------------------------------
def tampilkan_error(errors, batas=8):
    st.error("File tidak bisa dimuat:")
    for e in errors[:batas]:
        st.write(f"- {e}")
    if len(errors) > batas:
        st.caption(f"…dan {len(errors) - batas} masalah lain.")


def bagian_muat(U):
    n = st.session_state.upload_n
    berkas = st.file_uploader("Pilih file cadangan (.json atau .csv)", type=["json", "csv"], key=f"upload_{n}")
    st.caption("JSON memuat jurnal + daftar akun. CSV memuat jurnal; akun baru ditambahkan otomatis bila kolom Kategori & Saldo Normal ada.")
    if berkas is None:
        return
    if berkas.size > 5_000_000:
        st.error("File terlalu besar (maksimal 5 MB).")
        return

    isi = berkas.getvalue()
    try:
        if berkas.name.lower().endswith(".json"):
            data, errors = ak.muat_snapshot_json(isi.decode("utf-8-sig"))
        else:
            data, errors = ak.muat_snapshot_csv(isi, U["coa"])
    except UnicodeDecodeError:
        data, errors = None, ["Isi file bukan teks UTF-8 yang valid."]
    if errors:
        tampilkan_error(errors)
        return

    tgl = [t["tanggal"] for t in data["jurnal"]]
    p1, p2, p3 = st.columns(3)
    p1.metric("Transaksi", len(data["jurnal"]))
    p2.metric("Akun", len(data["coa"]))
    p3.metric("Rentang tanggal", f"{min(tgl)} → {max(tgl)}" if tgl else "-")
    if data["dibuat"]:
        st.caption(f"Cadangan dibuat {data['dibuat']}" + (f" oleh @{data['pengguna']}" if data["pengguna"] else "") + ".")
    st.success("✅ File valid: semua akun dikenali dan setiap transaksi seimbang.")

    yakin = True
    if U["jurnal"]:
        st.warning(f"Data saat ini ({len(U['jurnal'])} transaksi) akan DIGANTI oleh isi file ini.")
        yakin = st.checkbox("Saya mengerti dan ingin mengganti data saat ini")
    if st.button("📂 Muat data ini", type="primary", disabled=not yakin):
        U["jurnal"][:] = data["jurnal"]
        U["coa"][:] = data["coa"]
        ubah_data(U)
        U["komentar"] = data["komentar"]
        U["versi_cadangan"] = U["versi"]
        st.session_state.upload_n += 1
        st.session_state.pesan_sukses = f"✅ {len(data['jurnal'])} transaksi berhasil dimuat dari cadangan."
        st.rerun()


def halaman_cadangan(U):
    judul("💾", "Cadangan & ekspor", "Simpan data sesi agar bisa dimuat kembali setelah halaman dimuat ulang atau berpindah sesi.")
    jurnal = U["jurnal"]
    st.markdown(
        '<div class="kartu"><h4>Mengapa perlu cadangan?</h4>'
        "<p>Data tersimpan di memori sesi browser. Jika halaman di-refresh, sesi tertidur, atau kamu membuka "
        "sesi baru, data hilang. Unduh cadangan JSON, lalu muat kembali di sini kapan saja.</p></div>",
        unsafe_allow_html=True,
    )

    tab_unduh, tab_muat = st.tabs(["⬇️ Unduh", "⬆️ Muat cadangan"])

    with tab_unduh:
        if not jurnal:
            st.info("Belum ada data untuk diunduh. Kamu tetap bisa memuat cadangan di tab sebelah.")
        else:
            js, cjs = snap(U)
            stempel = datetime.now().strftime("%Y%m%d")
            dasar = f"akunpintar_{st.session_state.user['username']}_{stempel}"

            st.markdown("**Cadangan sesi (bisa dimuat kembali)**")
            c1, c2 = st.columns(2)
            snapshot = ak.snapshot_ke_json(
                ak.buat_snapshot(jurnal, U["coa"], st.session_state.user["username"], U["komentar"])
            )
            c1.download_button(
                "💾 Cadangan JSON (lengkap)",
                data=snapshot.encode("utf-8"),
                file_name=f"{dasar}.json",
                mime="application/json",
                type="primary",
                on_click=tandai_cadangan,
            )
            c2.download_button(
                "🧾 Cadangan CSV (jurnal)",
                data=ak.jurnal_ke_csv(jurnal, U["coa"]),
                file_name=f"{dasar}.csv",
                mime="text/csv",
                on_click=tandai_cadangan,
            )
            st.caption("JSON berisi jurnal, daftar akun, dan komentar AI. CSV berisi jurnal beserta kode/kategori akun yang dipakai.")

            st.markdown("**Laporan Excel**")
            st.download_button(
                "📥 Unduh laporan Excel (.xlsx)",
                data=buat_excel(js, cjs),
                file_name=f"{dasar}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            st.caption("Excel berisi Jurnal Umum, Buku Besar, Neraca Saldo, Laba Rugi, dan Posisi Keuangan. Untuk dibaca, bukan untuk dimuat kembali.")

    with tab_muat:
        bagian_muat(U)


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
    M_AKUN: halaman_akun,
    M_CADANGAN: halaman_cadangan,
}

pasang_css()
init_state()

if not st.session_state.user:
    halaman_masuk()
    st.stop()

U = data_user()
sidebar(U)

if st.session_state.pesan_sukses:
    st.success(st.session_state.pesan_sukses)
    st.session_state.pesan_sukses = ""

HALAMAN[st.session_state.menu](U)
