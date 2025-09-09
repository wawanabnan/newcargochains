# Ringkasan Wizard Freight Quotation (per 09 Sep)

## Masalah yang sudah jelas
1. **Format tanggal salah**
   - Sekarang input `valid_until` masih format default `YYYY-MM-DD`.
   - Yang diinginkan: **DD-MM-YY**.

2. **Tanggal default `valid_until` kosong**
   - Seharusnya otomatis terisi: **tanggal hari ini + nilai dari Setting `QUO_VALID_DAYS`** (contoh 7 hari).
   - Logika ini sudah ditulis di views, tapi di UI tetap kosong.

3. **TinyMCE terlalu pendek**
   - Height sudah diubah (`autoresize_min_height: 420`), tapi tidak ada efek → editor masih pendek.
   - Harus dipastikan pakai `height: ...` (bukan hanya autoresize), atau override CSS editor-body.

4. **Save / Finish (Step Lines) belum dites**
   - Belum ada validasi apakah data header + cargo berhasil benar-benar tersimpan.
   - Terakhir masih muncul error karena field `date` tidak diisi (`NOT NULL constraint failed`), sudah ditambahkan patch di views untuk isi `date=timezone.now()`.
   - Belum diverifikasi apakah proses ini sekarang berjalan sampai selesai.

---

## PR yang belum selesai
- **Tanggal `valid_until`**:
  - harus auto-terisi saat GET header (today + Setting QUO_VALID_DAYS).
  - format di input & datepicker harus **dd-mm-yy**, bukan `YYYY-MM-DD`.
- **TinyMCE height**:
  - atur agar benar-benar tinggi (pakai opsi `height: 400` atau override CSS editor iframe).
- **Save/Finish step Lines**:
  - perlu dites end-to-end, termasuk apakah cargo lines tersimpan dan status quotation valid.

---

## Rekomendasi teknis untuk session baru
- Gunakan **Flatpickr** dengan opsi `dateFormat: "d-m-y"` agar sesuai requirement.
- TinyMCE: pakai `height: 400` (atau lebih) langsung di config, jangan hanya `autoresize_min_height`.
- Pastikan field `date` di `FreightQuotation` diisi otomatis (`timezone.now().date()`).
- Lakukan uji coba end-to-end: buat Header → Next ke Lines → tambahkan Cargo → Finish → cek database.
