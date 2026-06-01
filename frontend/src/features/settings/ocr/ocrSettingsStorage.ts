/** localStorage key for system settings → model providers → OCR. */
export const OCR_SETTINGS_STORAGE_KEY = 'minerva.settings.ocr.v1'

export type OcrSettingsForm = {
  mode: 'disabled' | 'http'
  baseUrl: string
  apiKey: string
  timeoutSec: number
}

const defaultOcr: OcrSettingsForm = {
  mode: 'disabled',
  baseUrl: '',
  apiKey: '',
  timeoutSec: 30,
}

export function readOcrSettings(): OcrSettingsForm {
  try {
    const raw = localStorage.getItem(OCR_SETTINGS_STORAGE_KEY)
    if (!raw) return defaultOcr
    const parsed = JSON.parse(raw) as Partial<OcrSettingsForm>
    return { ...defaultOcr, ...parsed }
  } catch {
    return defaultOcr
  }
}

export function writeOcrSettings(value: OcrSettingsForm) {
  localStorage.setItem(OCR_SETTINGS_STORAGE_KEY, JSON.stringify(value))
}

export function clearOcrSettings() {
  localStorage.removeItem(OCR_SETTINGS_STORAGE_KEY)
}
