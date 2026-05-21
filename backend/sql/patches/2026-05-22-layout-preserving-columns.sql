-- Layout-preserving OCR / translate: add LDM columns to existing tables.
-- Idempotent; safe to run multiple times. Apply after pulling layout feature code.

ALTER TABLE public.doc_translate_job
  ADD COLUMN IF NOT EXISTS layout_snapshot_json jsonb NULL,
  ADD COLUMN IF NOT EXISTS layout_source varchar(32) NULL;

COMMENT ON COLUMN public.doc_translate_job.layout_snapshot_json IS '抽取完成后的 LDM 快照';
COMMENT ON COLUMN public.doc_translate_job.layout_source IS 'native / ocr / hybrid';

ALTER TABLE public.ocr_file_paddleocr
  ADD COLUMN IF NOT EXISTS page_width int4 NULL,
  ADD COLUMN IF NOT EXISTS page_height int4 NULL,
  ADD COLUMN IF NOT EXISTS layout_blocks_json jsonb NULL,
  ADD COLUMN IF NOT EXISTS page_raster_object_key varchar(1024) NULL,
  ADD COLUMN IF NOT EXISTS layout_version int2 NULL DEFAULT 1;

COMMENT ON COLUMN public.ocr_file_paddleocr.page_width IS '页宽（像素）';
COMMENT ON COLUMN public.ocr_file_paddleocr.page_height IS '页高（像素）';
COMMENT ON COLUMN public.ocr_file_paddleocr.layout_blocks_json IS 'LayoutBlock[] 真源';
COMMENT ON COLUMN public.ocr_file_paddleocr.page_raster_object_key IS '页图 S3 object_key';
COMMENT ON COLUMN public.ocr_file_paddleocr.layout_version IS 'LDM schema 版本';

ALTER TABLE public.ocr_file_mineru
  ADD COLUMN IF NOT EXISTS page_width int4 NULL,
  ADD COLUMN IF NOT EXISTS page_height int4 NULL,
  ADD COLUMN IF NOT EXISTS layout_blocks_json jsonb NULL,
  ADD COLUMN IF NOT EXISTS page_raster_object_key varchar(1024) NULL,
  ADD COLUMN IF NOT EXISTS layout_version int2 NULL DEFAULT 1;

COMMENT ON COLUMN public.ocr_file_mineru.page_width IS '页宽（像素）';
COMMENT ON COLUMN public.ocr_file_mineru.page_height IS '页高（像素）';
COMMENT ON COLUMN public.ocr_file_mineru.layout_blocks_json IS 'LayoutBlock[] 真源';
COMMENT ON COLUMN public.ocr_file_mineru.page_raster_object_key IS '页图 S3 object_key';
COMMENT ON COLUMN public.ocr_file_mineru.layout_version IS 'LDM schema 版本';
