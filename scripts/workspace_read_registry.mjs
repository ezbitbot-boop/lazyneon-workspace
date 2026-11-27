import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
export const readScripts={
  "scripts/audio_survey.py": "audio-survey",
  "scripts/extract_hwpx.py": "hwpx",
  "scripts/doc_diff.py": "doc-diff",
  "scripts/dlp_log_table.py": "dlp",
  "scripts/merge_timeline.py": "timeline",
  "scripts/verify_report.py": "verify",
  "scripts/evidence_manifest.py": "manifest",
  "scripts/case_survey.py": "scan",
  "scripts/scan_evidence.py": "scan",
  "scripts/court_evidence_sheet.py": "sheet",
  "scripts/evidence_export.py": "export",
  "scripts/local_stt.py": "stt",
  "scripts/local_ocr.py": "ocr",
  "scripts/pii_mask.py": "pii",
  "scripts/case_mode.mjs": "case-mode",
  "scripts/parse_ntfs_artifacts.py": "ntfs",
  "scripts/signature_check.py": "sig",
  "scripts/dedup_files.py": "dedup",
  "scripts/image_similarity.py": "similar",
  "scripts/exif_audit.py": "exif",
  "scripts/keyword_report.py": "kw",
  "scripts/archive_survey.py": "archive",
  "scripts/pdf_audit.py": "pdf",
  "scripts/sqlite_survey.py": "db",
  "scripts/video_integrity.py": "vcheck",
  "scripts/video_fingerprint.py": "vfp",
  "scripts/audio_fingerprint.py": "afp",
  "scripts/analyze_deepfake_evidence.py": "deepfake",
  "scripts/parse_korean_doc.py": "doc",
  "scripts/analyze_court_ruling.py": "ruling",
  "scripts/trace_financial_flow.py": "flow",
  "scripts/query_evidence_db.py": "db",
  "scripts/audit_evidence_integrity.py": "integrity",
  "scripts/certify_evidence_file.py": "certify",
  "scripts/korean_morph_grounding.py": "morph",
  "scripts/citation_grounding.py": "cite",
  "skills/forensic-audit/scripts/audit_timestamps.py": "timestamps",
  "skills/forensic-video/scripts/forensic_video_audit.py": "video",
  "skills/telegram-chat-extractor/scripts/parse_telegram.py": "telegram"
};
export function documentedReadSubcommand(script,workspace) {
 const normalized=script.replaceAll('\\','/');
 for(const [rel,sub] of Object.entries(readScripts)) {
  try {if(fs.realpathSync(path.resolve(workspace,normalized))===fs.realpathSync(path.join(root,rel)))return sub;}
  catch {if(normalized===rel)return sub;}
 }
 return null;
}
export const readFlags={
    'audio-survey':['--threshold','--json'],
    hwpx:['-o','--outdir','--json'],
    'doc-diff':['--markdown','--json','-o','--output','--all'],
    dlp:['--time-col','--event-col','--src-col','--phase-col','-o','--output'],
    timeline:['--manifest','--exif','--stt','--plaso','--anchor','-o','--output','--report'],
    manifest:['--protect','-o','--output','--verify'],verify:['--evidence','--json','--timeline','--sources','--require-sources','--morph-grounding','--claim-ledger'],
    scan:['-o','--output','--markdown','--keywords','--stt','--upload-audio'],sig:['--json','-o','--output'],timestamps:['--json','-o','--output'],exif:['--json','-o','--output'],
    pii:['--mask','-o','--output','--names','--addresses','--json','--in-place'],
    stt:['--out','--output','--out-dir','--allow-local-whisper','--allow-model-download','--upload-audio','--engine','--model','--lang','--keywords','--verbatim'],
    ocr:['--out','--output','--engine','--lang','--allow-model-download','--keywords'],
    export:['-o','--output','--party','--start','--purpose','--purpose-file','--case-id','--evidence-id'],
    sheet:['-o','--output','--party','--start','--purpose','--purpose-file'],
    bind:['-i','--input-json','-o','--output','--max-mb','--skip-non-pdf'],
    stamp:['-o','--output','-l','--label'],ntfs:['--json','-o','--output','-a','--artifact','--limit'],
    dedup:["--json", "--no-similar"],
    similar:["--query", "--threshold", "--json"],
    kw:["--context", "--json", "-o", "--output"],
    archive:["--json"],
    pdf:["--json"],
    db:["--json", "--sample", "--sql", "--list-schema", "--keywords", "--verify-hits", "--verify-report", "--export-axiom-counts", "--scan-insider-prompts", "--scan-git-dir", "--format", "--limit", "--output", "-o"],
    vcheck:["--json", "--no-decode"],
    vfp:["--compare", "--scan", "--samples", "--threshold", "--json"],
    afp:["--compare", "--threshold", "--json"],
    video:["--json"],
    deepfake:["--output", "-o", "--json", "--plot-fft"],
    mft:["--json", "-o", "--output", "-a", "--artifact", "--limit"],
    doc:["--output", "-o", "--markdown", "-m", "--json", "--strict", "--engine"],
    ruling:["--output", "-o", "--json", "--verify", "--source", "--morph-grounding", "--high-fidelity", "--strict"],
    flow:["--output", "-o", "--window-days", "--top", "--ctr-threshold", "--drain-hours"],
    integrity:["--scan-dir", "--file", "--report", "--algorithms", "--output", "-o", "--output-json"],
    certify:["--url", "--note", "--case", "--output", "--output-md", "--reviewer"],
    morph:["--source", "--target", "--text", "--threshold", "--filter-procedural", "--high-fidelity", "--old-korean", "--json"],
    cite:["--evidence", "--format", "--json", "--strict", "--max-hash-mb"],
    telegram:["--output", "-o", "--events-out", "--keyword", "-k", "--sender", "-s", "--summary"],
};
