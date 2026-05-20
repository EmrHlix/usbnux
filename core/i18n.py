"""Hafif i18n: gettext bağımlılığı olmadan dict tabanlı çeviri.

Kullanım:
    from core.i18n import _, set_language, get_language
    _('btn.browse')                          # -> "Gözat" veya "Browse"
    _('writer.progress', written=12, total=80) # -> "Yazılıyor: 12 / 80 MB"

Anahtar yoksa anahtar adı döner (gözle yakalanır, çökmez).
"""

LANGUAGES = ('tr', 'en')
LANGUAGE_LABELS = {'tr': 'Türkçe', 'en': 'English'}
DEFAULT_LANGUAGE = 'tr'

_current = DEFAULT_LANGUAGE


TRANSLATIONS = {
    # ── Pencere başlığı ─────────────────────────────────────────────
    'window.title': {'tr': 'USBnux', 'en': 'USBnux'},

    # ── Sayfa adları (ViewSwitcher) ─────────────────────────────────
    'page.write':   {'tr': 'ISO Yaz',     'en': 'Write ISO'},
    'page.dump':    {'tr': 'USB→ISO Çek', 'en': 'Dump USB'},
    'page.format':  {'tr': 'Formatla',    'en': 'Format'},

    # ── Genel butonlar ──────────────────────────────────────────────
    'btn.browse':       {'tr': 'Gözat',          'en': 'Browse'},
    'btn.refresh':      {'tr': 'Yenile',         'en': 'Refresh'},
    'btn.cancel':       {'tr': 'İptal',          'en': 'Cancel'},
    'btn.verify':       {'tr': 'Doğrula',        'en': 'Verify'},
    'btn.stop':         {'tr': 'Durdur',         'en': 'Stop'},
    'btn.write':        {'tr': '  Yaz  ',        'en': '  Write  '},
    'btn.dump':         {'tr': '  Çek  ',        'en': '  Dump  '},
    'btn.format':       {'tr': '  Formatla  ',   'en': '  Format  '},
    'btn.ok':           {'tr': 'Tamam',          'en': 'OK'},
    'btn.understood':   {'tr': 'Anladım',        'en': 'Got it'},
    'btn.save':         {'tr': 'Kaydet',         'en': 'Save'},
    'btn.select':       {'tr': 'Seç',            'en': 'Select'},
    'btn.pick_output':  {'tr': 'Konum seç',      'en': 'Choose location'},
    'btn.start':        {'tr': 'Başlat',         'en': 'Start'},

    # ── Header menüsü ───────────────────────────────────────────────
    'menu.view':            {'tr': 'Görünüm',        'en': 'Appearance'},
    'menu.view.system':     {'tr': 'Sistem teması',  'en': 'Follow system'},
    'menu.view.light':      {'tr': 'Açık tema',      'en': 'Light'},
    'menu.view.dark':       {'tr': 'Koyu tema',      'en': 'Dark'},
    'menu.language':        {'tr': 'Dil',            'en': 'Language'},
    'menu.about':           {'tr': 'Hakkında',       'en': 'About'},

    # ── ISO Yaz sayfası ─────────────────────────────────────────────
    'write.iso_group':      {'tr': 'ISO Dosyası',          'en': 'ISO File'},
    'write.iso_none':       {'tr': 'Dosya seçilmedi',      'en': 'No file selected'},
    'write.iso_hint':       {'tr': 'Gözat butonuna tıklayın veya pencereye sürükleyin',
                             'en': 'Click Browse or drag a file onto the window'},
    'write.drive_group':    {'tr': 'Hedef USB Sürücü',     'en': 'Target USB Drive'},
    'write.drive_label':    {'tr': 'Sürücü',               'en': 'Drive'},
    'write.opts_group':     {'tr': 'Seçenekler',           'en': 'Options'},
    'write.scheme':         {'tr': 'Bölüm Şeması',         'en': 'Partition Scheme'},
    'write.scheme_hint':    {'tr': 'MBR → Eski BIOS   /   GPT → Modern UEFI',
                             'en': 'MBR → Legacy BIOS   /   GPT → Modern UEFI'},
    'write.iso_type':       {'tr': 'ISO Türü',             'en': 'ISO Type'},
    'write.cks':            {'tr': 'Bütünlük (Checksum)',  'en': 'Integrity (Checksum)'},
    'write.cks_pick_iso':   {'tr': 'Bir ISO seçin',        'en': 'Select an ISO first'},
    'write.cks_searching':  {'tr': 'Sidecar dosyası aranıyor…',
                             'en': 'Looking for sidecar file…'},
    'write.cks_none':       {'tr': "Sidecar bulunamadı — beklenen hash'i elle girin",
                             'en': 'No sidecar found — enter the expected hash manually'},
    'write.cks_found':      {'tr': '{algo} bulundu: {prefix}… (yan dosya: {src})',
                             'en': '{algo} found: {prefix}… (sidecar: {src})'},
    'write.cks_progress':   {'tr': '{algo} hesaplanıyor… %{pct:.0f}  ({done} / {total})',
                             'en': 'Computing {algo}… {pct:.0f}%  ({done} / {total})'},
    'write.cks_match':      {'tr': '✓ {algo} eşleşti — ISO bütünlüğü doğrulandı',
                             'en': '✓ {algo} matches — ISO integrity verified'},
    'write.cks_mismatch':   {'tr': '✗ {algo} UYUŞMADI — beklenen {expected}…, bulunan {got}…',
                             'en': '✗ {algo} MISMATCH — expected {expected}…, got {got}…'},
    'write.cks_cancelled':  {'tr': 'Doğrulama iptal edildi', 'en': 'Verification cancelled'},
    'write.cks_invalid':    {'tr': 'Geçersiz hash — hex değer ve doğru uzunluk gerekli',
                             'en': 'Invalid hash — hex value with correct length required'},
    'write.cks_error':      {'tr': 'Hata: {error}',          'en': 'Error: {error}'},
    'write.status_group':   {'tr': 'Durum',                 'en': 'Status'},
    'write.status_ready':   {'tr': 'Hazır.',                'en': 'Ready.'},
    'write.confirm_title':  {'tr': 'DİKKAT — Veri Silinecek!',
                             'en': 'WARNING — Data Will Be Erased!'},
    'write.confirm_body':   {'tr': 'Aşağıdaki sürücüdeki TÜM VERİLER silinecektir:\n\n  {drive}\n\nDevam etmek istiyor musunuz?',
                             'en': 'ALL DATA on the following drive will be erased:\n\n  {drive}\n\nDo you want to continue?'},
    'write.confirm_cks_fail': {'tr': '⚠️  ISO checksum doğrulaması BAŞARISIZ — bu dosya bozuk veya kurcalanmış olabilir.\n\n',
                               'en': '⚠️  ISO checksum verification FAILED — this file may be corrupted or tampered with.\n\n'},
    'write.opt_bypass':     {'tr': 'Windows 11 kısıtlamalarını atla (TPM 2.0 / Secure Boot / RAM)',
                             'en': 'Bypass Windows 11 restrictions (TPM 2.0 / Secure Boot / RAM)'},
    'write.opt_bypass_only_win': {'tr': 'Sadece Windows ISO için geçerli',
                                  'en': 'Windows ISO only'},
    'write.opt_verify':     {'tr': 'Yazma sonrası doğrula (yazma süresine ~%50 ekler)',
                             'en': 'Verify after write (adds ~50% to the write time)'},
    'write.iso_type.win':   {'tr': '🪟  Windows ISO',       'en': '🪟  Windows ISO'},
    'write.iso_type.linux': {'tr': '🐧  Linux ISO',         'en': '🐧  Linux ISO'},

    # ── Verify hash diyaloğu ────────────────────────────────────────
    'verify.title':         {'tr': 'Checksum Doğrulama',    'en': 'Checksum Verification'},
    'verify.body':          {'tr': 'Beklenen hash değerini girin. Uzunluğa göre algoritma otomatik tespit edilir (MD5/SHA1/SHA256/SHA512).',
                             'en': 'Enter the expected hash value. The algorithm is auto-detected by length (MD5/SHA1/SHA256/SHA512).'},
    'verify.placeholder':   {'tr': 'örn. 2bf3a... (hex)',   'en': 'e.g. 2bf3a... (hex)'},
    'verify.prefill':       {'tr': 'Yan dosyadan ön-doldurma: {algo} ({src})',
                             'en': 'Pre-filled from sidecar: {algo} ({src})'},
    'verify.no_prefill':    {'tr': 'Yan dosya bulunamadı; değeri yapıştırın.',
                             'en': 'No sidecar found; paste the value.'},

    # ── ISO chooser ─────────────────────────────────────────────────
    'chooser.iso_title':    {'tr': 'ISO Dosyası Seç',       'en': 'Select ISO File'},
    'chooser.iso_filter':   {'tr': 'ISO Dosyaları (*.iso)', 'en': 'ISO Files (*.iso)'},
    'chooser.all_files':    {'tr': 'Tüm Dosyalar',          'en': 'All Files'},
    'chooser.dump_title':   {'tr': 'Çıktı ISO dosyasını seçin',
                             'en': 'Choose output ISO file'},
    'chooser.dump_default': {'tr': 'usb_dump.iso',          'en': 'usb_dump.iso'},

    # ── Dump sayfası ────────────────────────────────────────────────
    'dump.source_group':    {'tr': 'Kaynak USB Sürücü',     'en': 'Source USB Drive'},
    'dump.detect_group':    {'tr': 'Algılama',              'en': 'Detection'},
    'dump.content_type':    {'tr': 'İçerik türü',           'en': 'Content type'},
    'dump.output_size':     {'tr': 'Çıktı boyutu',          'en': 'Output size'},
    'dump.output_group':    {'tr': 'Çıktı Dosyası',         'en': 'Output File'},
    'dump.output_none':     {'tr': 'Dosya seçilmedi',       'en': 'No file selected'},
    'dump.output_hint':     {'tr': 'Konum seç butonuyla bir hedef belirleyin',
                             'en': 'Pick a destination with the Choose location button'},
    'dump.detecting':       {'tr': 'Algılanıyor…',          'en': 'Detecting…'},
    'dump.iso9660_ok':      {'tr': '🐧  ISO9660 algılandı — yalnızca ISO boyutu okunur',
                             'en': '🐧  ISO9660 detected — only the ISO volume size will be read'},
    'dump.iso9660_none':    {'tr': '⚠️  ISO9660 bulunamadı — tüm aygıt boyutu okunur',
                             'en': '⚠️  No ISO9660 found — the entire device size will be read'},
    'dump.size_unknown':    {'tr': 'Bilinmiyor',            'en': 'Unknown'},
    'dump.confirm_title':   {'tr': 'USB → ISO Çekme',       'en': 'USB → ISO Dump'},
    'dump.confirm_body':    {'tr': 'Kaynak: {drive}\nÇıktı:  {output}\nBoyut:  {size}\n\nKaynak USB\'ye yazılmaz, yalnızca okunur.{warn}\n\nDevam edilsin mi?',
                             'en': 'Source: {drive}\nOutput: {output}\nSize:   {size}\n\nThe source USB will not be written to, only read.{warn}\n\nContinue?'},
    'dump.confirm_warn':    {'tr': '\n\n⚠️  Aygıtta ISO9660 bulunamadı; çıktı geçerli bir ISO olmayabilir ve tüm aygıt boyutunu kaplayacaktır.',
                             'en': '\n\n⚠️  No ISO9660 found on the device; the output may not be a valid ISO and will span the full device size.'},
    'dump.done':            {'tr': 'ISO başarıyla çıkarıldı:\n{path}',
                             'en': 'ISO dumped successfully:\n{path}'},
    'dump.sensitive_title': {'tr': 'Sistem dizini uyarısı',
                             'en': 'System directory warning'},
    'dump.sensitive_body':  {'tr': 'Seçilen konum bir sistem dizininin altında:\n\n  {path}\n\nBuraya yazmak sistemi bozabilir veya kritik dosyaların üzerine yazabilir. Devam etmek istediğinizden emin misiniz?',
                             'en': 'The selected location is inside a system directory:\n\n  {path}\n\nWriting here may damage your system or overwrite critical files. Are you sure you want to continue?'},
    'dump.sensitive_continue': {'tr': 'Yine de kullan',
                                'en': 'Use anyway'},

    # ── Format sayfası ──────────────────────────────────────────────
    'fmt.drive_group':      {'tr': 'Hedef USB Sürücü',      'en': 'Target USB Drive'},
    'fmt.opts_group':       {'tr': 'Seçenekler',            'en': 'Options'},
    'fmt.fs':               {'tr': 'Dosya Sistemi',         'en': 'Filesystem'},
    'fmt.fs_hint':          {'tr': 'FAT32: maks uyumluluk · NTFS: Windows · exFAT: büyük dosyalar · ext4: Linux',
                             'en': 'FAT32: max compatibility · NTFS: Windows · exFAT: large files · ext4: Linux'},
    'fmt.scheme':           {'tr': 'Bölüm Şeması',          'en': 'Partition Scheme'},
    'fmt.scheme_hint':      {'tr': 'MBR → Eski BIOS   /   GPT → Modern UEFI',
                             'en': 'MBR → Legacy BIOS   /   GPT → Modern UEFI'},
    'fmt.label':            {'tr': 'Birim Etiketi',         'en': 'Volume Label'},
    'fmt.label_hint':       {'tr': 'Boş bırakılırsa varsayılan kullanılır',
                             'en': 'Default is used when empty'},
    'fmt.label_placeholder':{'tr': 'USB',                   'en': 'USB'},
    'fmt.confirm_title':    {'tr': 'DİKKAT — Sürücü Formatlanacak!',
                             'en': 'WARNING — Drive Will Be Formatted!'},
    'fmt.confirm_body':     {'tr': 'Aşağıdaki sürücüdeki TÜM VERİLER kalıcı olarak silinecektir:\n\n  {drive}\n\nDosya sistemi: {fs}\nBölüm şeması:  {scheme}\nEtiket:        {label}\n\nDevam etmek istiyor musunuz?',
                             'en': 'ALL DATA on the following drive will be permanently erased:\n\n  {drive}\n\nFilesystem:      {fs}\nPartition scheme: {scheme}\nLabel:           {label}\n\nDo you want to continue?'},
    'fmt.done':             {'tr': 'USB başarıyla biçimlendirildi.\n\nDosya sistemi: {fs}\nEtiket: {label}\nBölüm şeması: {scheme}',
                             'en': 'USB formatted successfully.\n\nFilesystem: {fs}\nLabel: {label}\nPartition scheme: {scheme}'},

    # ── Drive listesi ───────────────────────────────────────────────
    'drives.none':          {'tr': 'USB sürücü bulunamadı', 'en': 'No USB drives found'},
    'misc.dash':            {'tr': '—',                     'en': '—'},

    # ── Genel status / writer.py mesajları ─────────────────────────
    'st.unmount':           {'tr': 'USB bağlantısı kesiliyor…', 'en': 'Unmounting USB…'},
    'st.iso_write':         {'tr': 'ISO yazılıyor…',         'en': 'Writing ISO…'},
    'st.writing_progress':  {'tr': 'Yazılıyor: {done:.0f} MB / {total:.0f} MB',
                             'en': 'Writing: {done:.0f} MB / {total:.0f} MB'},
    'st.sync':              {'tr': 'Diske aktarılıyor (sync)…', 'en': 'Flushing to disk (sync)…'},
    'st.partition_table':   {'tr': 'Bölüm tablosu oluşturuluyor…',
                             'en': 'Creating partition table…'},
    'st.fat32_format':      {'tr': 'FAT32 olarak biçimlendiriliyor…',
                             'en': 'Formatting as FAT32…'},
    'st.mount_iso':         {'tr': 'ISO bağlanıyor…',       'en': 'Mounting ISO…'},
    'st.mount_usb':         {'tr': 'USB bağlanıyor…',       'en': 'Mounting USB…'},
    'st.copying':           {'tr': 'Dosyalar kopyalanıyor…','en': 'Copying files…'},
    'st.copying_file':      {'tr': 'Kopyalanıyor: {file}',  'en': 'Copying: {file}'},
    'st.wim_split':         {'tr': 'install.wim bölünüyor ({size:.1f} GB > 4 GB sınırı)…',
                             'en': 'Splitting install.wim ({size:.1f} GB > 4 GB limit)…'},
    'st.bypass_inject':     {'tr': 'Windows 11 gereksinim atlama dosyası ekleniyor…',
                             'en': 'Adding Windows 11 bypass file…'},
    'st.verify_setup':      {'tr': 'Doğrulama: bağlantılar kuruluyor…',
                             'en': 'Verification: setting up mounts…'},
    'st.verify_swm':        {'tr': 'Doğrulama: install.swm dosyaları kontrol ediliyor…',
                             'en': 'Verification: checking install.swm files…'},
    'st.verify_file':       {'tr': 'Doğrulanıyor: {file}',  'en': 'Verifying: {file}'},
    'st.hashing_iso':       {'tr': 'ISO hashleniyor: {done:.0f} MB / {total:.0f} MB',
                             'en': 'Hashing ISO: {done:.0f} MB / {total:.0f} MB'},
    'st.hashing_usb':       {'tr': 'USB hashleniyor: {done:.0f} MB / {total:.0f} MB',
                             'en': 'Hashing USB: {done:.0f} MB / {total:.0f} MB'},
    'st.reading':           {'tr': 'Okunuyor…',             'en': 'Reading…'},
    'st.reading_progress':  {'tr': 'Okunuyor: {done:.0f} MB / {total:.0f} MB',
                             'en': 'Reading: {done:.0f} MB / {total:.0f} MB'},
    'st.wipe_sigs':         {'tr': 'Eski bölüm imzaları temizleniyor…',
                             'en': 'Wiping old partition signatures…'},
    'st.fmt_progress':      {'tr': '{fs} olarak biçimlendiriliyor (etiket: {label})…',
                             'en': 'Formatting as {fs} (label: {label})…'},
    'st.cancelling':        {'tr': 'İptal ediliyor…',       'en': 'Cancelling…'},

    # ── Sonuç başlıkları + mesajları ────────────────────────────────
    'res.success':          {'tr': 'Başarılı!',             'en': 'Success!'},
    'res.error':            {'tr': 'Hata!',                 'en': 'Error!'},
    'res.linux_done':       {'tr': 'Linux ISO başarıyla yazıldı!',
                             'en': 'Linux ISO written successfully!'},
    'res.linux_verified':   {'tr': '\nDoğrulama başarılı: USB içeriği ISO ile bit-bit aynı.',
                             'en': '\nVerification passed: USB matches ISO bit-by-bit.'},
    'res.win_done':         {'tr': 'Windows USB başarıyla oluşturuldu! (UEFI uyumlu)',
                             'en': 'Windows USB created successfully! (UEFI compatible)'},
    'res.win_bypass_note':  {'tr': '\n\nWindows 11 TPM 2.0 / RAM / Secure Boot kontrolleri atlanacak.',
                             'en': '\n\nWindows 11 TPM 2.0 / RAM / Secure Boot checks will be bypassed.'},
    'res.win_verified':     {'tr': '\n\nDoğrulama başarılı: dosya yapısı ISO ile eşleşiyor.',
                             'en': '\n\nVerification passed: file tree matches ISO.'},
    'res.elapsed':          {'tr': 'Toplam: {m}:{s:02d}',   'en': 'Total: {m}:{s:02d}'},
    'res.cancelled':        {'tr': 'İşlem kullanıcı tarafından iptal edildi.',
                             'en': 'Operation cancelled by user.'},

    # ── Genel hata mesajları ───────────────────────────────────────
    'err.partition_create': {'tr': 'Bölüm oluşturulamadı: {path}',
                             'en': 'Partition could not be created: {path}'},
    'err.mkfs_fail':        {'tr': '{fs} biçimlendirme başarısız: {detail}',
                             'en': '{fs} formatting failed: {detail}'},
    'err.mkfs_missing':     {'tr': '{fs} için mkfs aracı bulunamadı. Lütfen ilgili paketi kurun (FAT32: dosfstools, NTFS: ntfs-3g, exFAT: exfatprogs, ext4: e2fsprogs).',
                             'en': 'mkfs tool for {fs} not found. Please install the relevant package (FAT32: dosfstools, NTFS: ntfs-3g, exFAT: exfatprogs, ext4: e2fsprogs).'},
    'err.mkfs_fat':         {'tr': 'mkfs.fat başarısız: {detail}',
                             'en': 'mkfs.fat failed: {detail}'},
    'err.wim_split_fail':   {'tr': 'WIM bölme başarısız: {detail}',
                             'en': 'WIM split failed: {detail}'},
    'err.unsupported_fs':   {'tr': 'Desteklenmeyen dosya sistemi: {fs}',
                             'en': 'Unsupported filesystem: {fs}'},
    'err.wimtools_missing': {'tr': 'wimlib-imagex bulunamadı. 4 GiB üzerindeki install.wim dosyalarını bölmek için gerekli.\n\nKurmak için terminalde çalıştırın:\n  sudo apt install wimtools',
                             'en': 'wimlib-imagex not found. Required for splitting install.wim files larger than 4 GiB.\n\nTo install, run in a terminal:\n  sudo apt install wimtools'},
    'err.verify_linux':     {'tr': 'Doğrulama başarısız: USB içeriği ISO ile eşleşmiyor.\nISO SHA256: {iso_h}\nUSB SHA256: {usb_h}',
                             'en': 'Verification failed: USB does not match ISO.\nISO SHA256: {iso_h}\nUSB SHA256: {usb_h}'},
    'err.verify_win':       {'tr': 'Doğrulama başarısız ({count} fark):\n{preview}{more}',
                             'en': 'Verification failed ({count} differences):\n{preview}{more}'},
    'err.verify_win_more':  {'tr': '\n… ve {n} daha', 'en': '\n… and {n} more'},
    'err.verify_missing':   {'tr': 'eksik: {file}', 'en': 'missing: {file}'},
    'err.verify_size':      {'tr': 'boyut uyuşmadı ({file}): {actual} ≠ {expected}',
                             'en': 'size mismatch ({file}): {actual} ≠ {expected}'},
    'err.generic':          {'tr': 'Hata: {detail}', 'en': 'Error: {detail}'},

    # ── Drag & drop ──────────────────────────────────────────────────
    'dnd.invalid':          {'tr': 'Geçersiz dosya',        'en': 'Invalid file'},
    'dnd.iso_only':         {'tr': 'Sadece .iso uzantılı dosyalar kabul edilir.',
                             'en': 'Only .iso files are accepted.'},

    # ── Root uyarısı ─────────────────────────────────────────────────
    'root.title':           {'tr': 'Yetki Uyarısı', 'en': 'Permission Warning'},
    'root.body':            {'tr': "USB'ye yazma işlemi root yetkisi gerektirir.\n\nLütfen uygulamayı şu şekilde çalıştırın:\n  sudo python3 main.py",
                             'en': 'Writing to USB requires root privileges.\n\nPlease run the app as:\n  sudo python3 main.py'},

    # ── Dil değişikliği ─────────────────────────────────────────────
    'lang.busy_title':      {'tr': 'İşlem devam ediyor',
                             'en': 'Operation in progress'},
    'lang.busy_body':       {'tr': 'Yazma/çekme/formatlama bittikten sonra dili değiştirebilirsiniz.',
                             'en': 'You can change the language after the current operation finishes.'},
}


def set_language(lang):
    global _current
    if lang in LANGUAGES:
        _current = lang


def get_language():
    return _current


def _(key, **fmt):
    entry = TRANSLATIONS.get(key)
    if not entry:
        return key
    template = entry.get(_current) or entry.get(DEFAULT_LANGUAGE) or key
    if fmt:
        try:
            return template.format(**fmt)
        except (KeyError, IndexError):
            return template
    return template
