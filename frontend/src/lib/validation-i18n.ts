import type { ZodIssue } from "zod";

/**
 * Maps Zod field name + error code to an i18n key from the auth.validation namespace.
 * For password, distinguishes min(1) (required) vs min(8) (too short) by checking the minimum value.
 */
const PASSWORD_REGEX_MAP: Record<string, string> = {
  "uppercase": "passwordUppercase",
  "lowercase": "passwordLowercase",
  "digit": "passwordDigit",
};

const ZOD_ERROR_MAP: Record<string, Record<string, string>> = {
  email: {
    too_small: "emailRequired",
    invalid_string: "emailInvalid",
    invalid_format: "emailInvalid",
  },
  password: {
    too_small: "passwordRequired",
  },
  full_name: {
    too_small: "fullNameRequired",
  },
  faculty: {
    too_small: "facultyRequired",
  },
  current_password: {
    too_small: "currentPasswordRequired",
  },
  new_password: {
    too_small: "passwordMinLength",
    invalid_string: "passwordMinLength",
  },
  confirm_password: {
    too_small: "confirmPasswordRequired",
    custom: "passwordsDoNotMatch",
  },
};

export function mapZodErrors(
  issues: ZodIssue[],
  t: (key: string) => string
): Record<string, string> {
  const errors: Record<string, string> = {};

  for (const issue of issues) {
    const field = String(issue.path[0]);
    if (errors[field]) continue;

    // Map password/new_password regex validation errors to i18n keys
    if ((field === "password" || field === "new_password") && "validation" in issue) {
      for (const [keyword, i18nKey] of Object.entries(PASSWORD_REGEX_MAP)) {
        if (issue.message.toLowerCase().includes(keyword)) {
          errors[field] = t(i18nKey);
          break;
        }
      }
      if (errors[field]) continue;
    }

    const fieldMap = ZOD_ERROR_MAP[field];
    if (fieldMap) {
      if (field === "password" && issue.code === "too_small" && "minimum" in issue) {
        const minimum = issue.minimum as number;
        errors[field] = t(minimum > 1 ? "passwordMinLength" : "passwordRequired");
        continue;
      }

      if (field === "new_password" && issue.code === "too_small" && "minimum" in issue) {
        const minimum = issue.minimum as number;
        errors[field] = t(minimum > 1 ? "passwordMinLength" : "passwordRequired");
        continue;
      }

      const key = fieldMap[issue.code];
      if (key) {
        errors[field] = t(key);
        continue;
      }
    }

    errors[field] = issue.message;
  }

  return errors;
}
