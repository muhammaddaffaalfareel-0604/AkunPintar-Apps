# 📒 JurnalAI – Asisten Jurnal Otomatis dari Kalimat Biasa

> Nama: **(isi namamu)** · Mata kuliah: **(isi)** · Dosen: **(isi)**

Aplikasi web yang mengubah kalimat transaksi sehari-hari menjadi jurnal umum, lalu
membentuk buku besar, neraca saldo, dan laporan keuangan secara otomatis.

🔗 **Aplikasi:** (tempel link Streamlit di sini)

## Latar Belakang
Pencatatan jurnal manual membutuhkan pemahaman akun dan rawan salah debit/kredit,
terutama bagi pelaku UMKM dan mahasiswa. (Tambahkan 2–3 kalimat dengan kata-katamu sendiri.)

## Cara Kerja
````
Kalimat transaksi → AI menyusun draf jurnal → Python memvalidasi (debit = kredit)
→ pengguna meninjau/mengedit → Jurnal Umum → Buku Besar → Neraca Saldo
→ Laporan Keuangan → Ekspor Excel
````

### Pembagian Tugas AI dan Python
| Tugas | Dikerjakan oleh |
|---|---|
| Memahami kalimat, memilih akun | AI (Groq, model `openai/gpt-oss-20b`) |
| Validasi debit = kredit, akun sesuai daftar | Python |
| Buku besar, neraca saldo, laporan keuangan | Python (pandas) |
| Komentar atas laporan | AI (dari angka hasil hitungan Python) |

AI **tidak pernah menghitung saldo**. Jika AI salah, Python menolak dan meminta AI memperbaiki
(maksimal 2 kali). Pengguna juga wajib menyetujui draf sebelum masuk ke jurnal.

## Fitur
- Input transaksi bahasa biasa (beberapa transaksi sekaligus)
- Agent bertanya balik jika informasi kurang jelas
- Tinjau dan edit draf jurnal (human-in-the-loop)
- Jurnal umum, buku besar per akun, neraca saldo
- Laporan laba rugi dan posisi keuangan sederhana + grafik
- Komentar AI dan ekspor ke Excel

## Landasan Teori
- Persamaan dasar akuntansi: Aset = Liabilitas + Ekuitas
- Siklus akuntansi: transaksi → jurnal → buku besar → neraca saldo → laporan keuangan
- Prinsip pencatatan berpasangan (double-entry): total debit = total kredit
- (Tambahkan referensi buku/standar yang kamu pakai, dan verifikasi ke sumber resminya.)

## Teknologi
Python · Streamlit · pandas · Plotly · Groq API · GitHub

## Cara Menjalankan
1. Buat repository GitHub dan unggah: `app.py`, `akuntansi.py`, `requirements.txt`.
2. Deploy di Streamlit Community Cloud (main file: `app.py`).
3. Di **Advanced settings → Secrets** isi: `GROQ_API_KEY = "kunci_groq_kamu"`.
4. Jangan pernah menaruh API Key di kode atau di GitHub.

## Batasan
- AI bisa salah memilih akun, sehingga tinjauan manusia wajib.
- Cakupan: transaksi dasar. Jurnal penyesuaian akhir periode (penyusutan, akrual), PPN, dan
  pajak belum didukung.
- Data hanya tersimpan selama aplikasi dibuka; unduh Excel sebelum menutup halaman.
- Daftar akun dapat diubah di `akuntansi.py` (bagian `AKUN`).
````
````

Kalau mau, saya bisa bantu juga mengisi bagian README yang masih kosong (nama, latar belakang, landasan teori) atau memeriksa kode ini untuk bug dan perbaikan.
