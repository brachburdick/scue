import type { ButtonHTMLAttributes } from "react";

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    "bg-blue-600 hover:bg-blue-500 text-white",
  secondary:
    "bg-gray-700 hover:bg-gray-600 text-gray-100",
  danger:
    "bg-red-600 hover:bg-red-500 text-white",
  ghost:
    "text-gray-400 hover:text-gray-200",
};

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonProps) {
  const base =
    variant === "ghost"
      ? "text-sm disabled:opacity-50"
      : "px-3 py-1.5 text-sm rounded disabled:opacity-50";

  return (
    <button
      className={`${base} ${variantClasses[variant]} ${className}`}
      {...props}
    />
  );
}
