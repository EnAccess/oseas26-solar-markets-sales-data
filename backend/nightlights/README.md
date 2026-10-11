# Nightlights API

NASA Black Marble nighttime lights, streamed live from NASA's LAADS archive.
Nothing is downloaded to disk. No local copies. No cache to clear.

This is the **nightlights feature layer** for the solar-markets model. It is one
input among several (population, wealth, grid infrastructure). It is not a measure
of electricity access and must not be described as one.

---

## What this gives you

For any coordinate on Earth, you get the nighttime radiance measured by the
VIIRS instrument on the Suomi-NPP satellite — the same data NASA publishes as
Black Marble.

Two audiences, two endpoints:

| Endpoint | Audience | Output |
|---|---|---|
| `GET /nightlights` | Humans, demos, docs | Plain-English summary with warnings |
| `GET /features` | The model | One flat row, short keys, ready for pandas |
| `POST /features/batch` | The model, at scale | Many rows, one NASA open per tile |

Plus four lower-level endpoints kept for anyone who needs them:
`/health`, `/resolve`, `/sample`, `/sample/batch`, `/area`.

---

## Run it

You need:
- Python 3.11 or newer (3.14 works but is bleeding-edge; 3.12 or 3.13 is safer)
- A NASA Earthdata token (see below)
- The packages in `requirements.txt`

### 1. Get a NASA Earthdata token

1. Register at https://urs.earthdata.nasa.gov if you don't have an account.
2. Log in, go to **Generate Token**, create one.
3. Copy it. You will paste it once, into a file, and never into code.

### 2. Put the token in `.env`

Create the file `backend/.env` (it's already gitignored, so it will never
be committed):
