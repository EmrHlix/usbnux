# USBnux

GTK4 / libadwaita desktop tool for **writing ISO images to USB drives**,
**dumping a USB back to an ISO file**, and **formatting USB drives**
(FAT32 / NTFS / exFAT / ext4) on Linux.

Built for Debian / Ubuntu / Mint and their derivatives.

---

## Features

- **Write** — flash Linux or Windows ISOs to USB
  - Auto-detects ISO type (Linux vs Windows) by inspecting boot files
  - For Windows: creates an MBR or GPT partition, formats FAT32, copies files,
    and automatically splits `install.wim` with `wimlib-imagex` when it
    exceeds the 4 GiB FAT32 limit
  - For Linux: plain `dd`-style raw block copy in 4 MiB chunks
  - Optional **Windows 11 bypass** (TPM 2.0 / Secure Boot / RAM checks) via
    `autounattend.xml`
  - Optional **post-write verification** (SHA-256 bit-by-bit for Linux,
    file tree + size for Windows)
  - Drag-and-drop ISO support
- **Checksum verification** — auto-detects sidecar files
  (`*.sha256`, `SHA256SUMS`, etc.) and verifies the ISO before writing
- **Dump** — read a USB back to an `.iso` file
  - Reads the ISO9660 Primary Volume Descriptor to write only the real
    volume size (not the whole device padding)
- **Format** — wipe and reformat USB drives
  - Filesystems: FAT32, NTFS, exFAT, ext4
  - Partition scheme: MBR or GPT
  - Custom volume label (sanitised per filesystem rules)

## Why does it need root?

USBnux works directly with raw block devices (`/dev/sdX`), calls `parted`,
`mkfs.*`, `wipefs`, `mount`/`umount` and `sync` — all of which require root
on Linux. There is no way around this for the kind of work the tool does.

To minimise the blast radius:

- USBnux **does not run setuid**. The desktop launcher invokes `pkexec` via
  the polkit policy in `io.github.usbnux.policy`, so you get a password
  prompt **once at launch** and the privileges are scoped to the running
  process.
- The pkexec wrapper redirects `XDG_CACHE_HOME` / `XDG_DATA_HOME` /
  `XDG_STATE_HOME` to a temporary directory so the root-owned process does
  not pollute your user cache.

If you would rather not run the GUI as root, well-supported alternatives
exist (GNOME Disks, Impression, balenaEtcher with a privileged helper).
USBnux deliberately follows the simpler "ask for root at launch" model used
by Rufus, dd and Fedora Media Writer.

## Installation

### From a `.deb` package (recommended)

```bash
git clone https://github.com/EmrHlix/usbnux.git
cd usbnux
./build-deb.sh
sudo apt install ./dist/usbnux_*_all.deb
```

`apt install` pulls every required dependency declared in the package's
`Depends:` field. After install, launch **USBnux** from your application
menu.

### From source

```bash
git clone https://github.com/EmrHlix/usbnux.git
cd usbnux
sudo ./install.sh         # installs apt dependencies
sudo python3 main.py      # or: sudo ./run.sh
```

## Runtime dependencies

| Package      | Used for                                              |
|--------------|-------------------------------------------------------|
| `python3`, `python3-gi`, `python3-gi-cairo` | runtime + GTK bindings |
| `gir1.2-gtk-4.0`, `gir1.2-adw-1`            | GTK 4 + libadwaita     |
| `parted`     | partition tables (`parted`, `partprobe`)              |
| `dosfstools` | `mkfs.fat` (FAT32)                                    |
| `ntfs-3g`    | `mkfs.ntfs` + NTFS mount support                      |
| `exfatprogs` | `mkfs.exfat`                                          |
| `e2fsprogs`  | `mkfs.ext4`                                           |
| `wimtools`   | `wimlib-imagex` for splitting `install.wim` > 4 GiB   |
| `genisoimage`, `p7zip-full` | ISO type detection fallbacks           |
| `util-linux` | `lsblk`, `mount`, `umount`, `sync`, `wipefs`          |
| `policykit-1` or `polkit` | pkexec privilege escalation              |

If `wimlib-imagex` is missing **and** a Windows ISO is being written that
contains a `> 4 GiB install.wim`, USBnux aborts with a clear error and
asks you to install `wimtools` manually (`sudo apt install wimtools`).
USBnux never invokes `apt` on your behalf — both the `.deb` package and
`install.sh` declare `wimtools` as a dependency, so this only happens if
you skipped them.

## Building the `.deb`

```bash
./build-deb.sh
```

Reads `Version`, `Architecture` and `Package` straight from
`packaging/debian/DEBIAN/control` and outputs
`dist/usbnux_<version>_all.deb`. The package is `Architecture: all`
because the codebase is pure Python.

## Project layout

```
usbnux/
├── main.py                 # entry point
├── core/                   # business logic, UI-independent
│   ├── checksum.py         # sidecar discovery + SHA/MD5
│   ├── disk_detector.py    # USB enumeration + unmount + size helpers
│   ├── dumper.py           # USB → ISO + ISO9660 PVD size detection
│   ├── formatter.py        # FAT32 / NTFS / exFAT / ext4 formatting
│   ├── iso_analyzer.py     # ISO type (windows vs linux) detection
│   └── writer.py           # raw write + Windows file-tree copy + WIM split
├── ui/main_window.py       # GTK 4 window, three-page ViewStack
├── packaging/debian/       # .deb skeleton (control, desktop, polkit, icon)
├── build-deb.sh            # builds dist/usbnux_<ver>_all.deb
└── install.sh              # apt dependency installer
```

## License

USBnux is released under the **GNU General Public License v3.0** — see
[LICENSE](LICENSE) for the full text. In short: you are free to use,
modify and redistribute USBnux, but derivative works must also be released
under GPL-3.

## Disclaimer

USBnux writes to and formats raw block devices. **Picking the wrong drive
will wipe it.** Always double-check the device path and size shown in the
drive picker before confirming a write or format. The authors accept no
liability for data loss.
