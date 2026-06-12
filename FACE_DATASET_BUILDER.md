# Face Dataset Builder

A small local desktop tool for building a face-recognition dataset for the humanoid robot project.

## Quick start

```bash
# Install dependency (if not already installed)
pip install Pillow

# Launch the GUI
python face_dataset_builder.py

# Run the dry-run self-test (no images or GUI needed)
python face_dataset_builder.py --test
```

## Dataset structure

```
face_data/
  photos/
    ali_valiyev/
      01.jpg
      02.jpg
    dilshod_karimov/
      01.jpg
  people.csv
  manifest.json
```

### `people.csv` columns

| Column | Example |
|---|---|
| `person_id` | `ali_valiyev` |
| `fio` | `Ali Valiyev` |
| `display_name` | `Ali aka` |
| `photo_dir` | `face_data/photos/ali_valiyev` |
| `created_at` | `2026-05-25T14:30:00` |
| `updated_at` | `2026-05-25T14:30:00` |
| `photo_count` | `2` |

### `manifest.json` fields

```json
{
  "schema_version": "1.0",
  "total_people": 2,
  "total_photos": 5,
  "last_updated_at": "2026-05-25T14:30:00",
  "photo_hashes": {
    "ali_valiyev": ["sha256hex...", "sha256hex..."]
  },
  "history": [
    {
      "timestamp": "...",
      "action": "add_person",
      "person_id": "ali_valiyev",
      "fio": "Ali Valiyev",
      "files_added": ["01.jpg"],
      "files_skipped": []
    }
  ]
}
```

## GUI workflow

1. Enter **FIO** (required) — e.g. `Ali Valiyev`
2. Enter **Display name** (optional) — e.g. `Ali aka`
3. Click **📂 Select Images** — choose one or more `.jpg/.jpeg/.png/.webp` files
4. Click **✅ Save / Add**

The app will:
- Generate `person_id` from FIO (`Ali Valiyev` → `ali_valiyev`)
- Create `face_data/photos/ali_valiyev/` if it doesn't exist
- Copy images as `01.jpg`, `02.jpg`, … (converted to JPEG via Pillow)
- Update `people.csv` and `manifest.json`
- Show results in the log panel

Clicking a row in the **Known People** table pre-fills the form for adding more photos.

## Duplicate prevention

- **Duplicate person**: same `person_id` → existing row is updated, not duplicated
- **Duplicate photo**: SHA-256 hash of each image is stored in `manifest.json`; if the same image is uploaded again it is skipped with a log message

## Servo direction calibration note

If a servo moves in the wrong direction, flip the sign of the corresponding offset in `.env`:

```
ARM_RIGHT_SHOULDER_RAISE_OFFSET=-55   # flip sign
```

## Dependencies

| Package | Purpose |
|---|---|
| `Pillow` | Image validation and JPEG conversion |
| `tkinter` | GUI (stdlib on Windows/macOS) |

On headless Linux: `sudo apt install python3-tk`
