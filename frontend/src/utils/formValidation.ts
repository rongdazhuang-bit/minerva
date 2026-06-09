/** Helpers for Ant Design Form.validateFields rejection payloads. */

type FormValidateError = {
  errorFields?: Array<{ errors: string[] }>
}

/** Return the first inline validation message from a validateFields rejection. */
export function getFirstFormValidationMessage(error: unknown): string | undefined {
  const fields = (error as FormValidateError)?.errorFields
  if (!fields?.length) return undefined
  for (const field of fields) {
    const msg = field.errors?.[0]
    if (msg) return msg
  }
  return undefined
}

/** Whether an unknown error value is an Ant Design form validation rejection. */
export function isFormValidationError(error: unknown): boolean {
  return getFirstFormValidationMessage(error) != null
}
