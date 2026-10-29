# Dataset provenance

Downloaded 2026-10-22 (America/Toronto).

File: soc-redditHyperlinks-title.tsv
Size: 368581209 bytes (351.5 MiB)
Original: https://snap.stanford.edu/data/soc-redditHyperlinks-title.tsv
Downloaded from: https://media.githubusercontent.com/media/Raphtory/Data/main/soc-redditHyperlinks-title.tsv
Verified MD5: e1babc01eb264be47cbab4fe134546de
Checksum reference: https://github.com/snap-stanford/roland/blob/master/get_roland_public_data.sh

The downloaded file matches the expected MD5 published by snap-stanford/roland.
The primary Stanford server reset connections, so the Raphtory mirror was used.
This note originally covered the title file only. The October 29 update below
records the body download and merged processing; both raw files remain unchanged.

A lossless gzip copy (`soc-redditHyperlinks-title.tsv.gz`) and this note are tracked
in Git. The original TSV is preserved locally without modification and ignored by
Git. Decompressing the archive was verified against the original MD5 above.
The archive fits GitHub's 100 MiB per-file limit without splitting the dataset.

## Body file and role A processing - October 29, 2026

Downloaded directly from:
https://snap.stanford.edu/data/soc-redditHyperlinks-body.tsv

Size: 318931394 bytes

Verified MD5: 4ed2bb05718498b66450a10216e29b86

SHA-256: 9bbf57511dc0da7369c2e896d865b68f170136def4f223f4c9e9e10818f4bfb5

Checksum reference (both files):
https://github.com/snap-stanford/roland/blob/master/get_roland_public_data.sh

The body file matches SNAP's published MD5. The title MD5 was rechecked as part
of the full run. `src/prepare_network.py` processes both raw files into
`data/processed/`; policy, hashes, raw and cleaned counts are in its manifest.
The report folder retains a small copy of that manifest and the statistics.
The raw body TSV and generated CSVs are local files ignored by Git.
