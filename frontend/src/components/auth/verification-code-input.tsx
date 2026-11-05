"use client";

import { useEffect, useRef } from "react";
import { normalizeVerificationCode } from "@/lib/verification-code.mjs";

type VerificationCodeInputProps = {
  value: string;
  onChange: (code: string) => void;
  disabled?: boolean;
  invalid?: boolean;
};

/** Six visual slots, one real input: reliable keyboard, paste and OTP autofill. */
export function VerificationCodeInput({
  value, onChange, disabled = false, invalid = false,
}: VerificationCodeInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  return (
    <div className="auth-code-field" data-invalid={invalid || undefined}>
      <label className="sr-only" htmlFor="mira-email-code">Código de verificação de seis dígitos</label>
      <input
        ref={inputRef}
        id="mira-email-code"
        className="auth-code-native-input"
        type="text"
        inputMode="numeric"
        autoComplete="one-time-code"
        autoCapitalize="off"
        autoCorrect="off"
        spellCheck={false}
        pattern="[0-9]{6}"
        minLength={6}
        maxLength={6}
        value={value}
        onChange={(event) => onChange(normalizeVerificationCode(event.target.value))}
        onFocus={(event) => { if (value.length === 6) event.currentTarget.select(); }}
        disabled={disabled}
        required
        aria-invalid={invalid}
        aria-describedby={invalid ? "auth-code-hint auth-login-error" : "auth-code-hint"}
      />
      <div className="auth-code-digits" aria-hidden="true">
        {Array.from({ length: 6 }, (_, index) => (
          <span
            key={index}
            className="auth-code-digit"
            data-active={index === Math.min(value.length, 5) || undefined}
          >
            {value[index] ?? ""}
          </span>
        ))}
      </div>
    </div>
  );
}
