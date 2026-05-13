-- One-time data fix: align legacy MinerU code with settings-page constant MINERU.
UPDATE public.ocr_file
SET ocr_type = 'MINERU'
WHERE ocr_type = 'MINER_U';
