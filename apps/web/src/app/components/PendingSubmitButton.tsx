"use client";

import { useFormStatus } from "react-dom";

type Props = { label: string; pendingLabel?: string; className?: string };

export default function PendingSubmitButton({ label, pendingLabel = "Saving…", className = "button button-primary" }: Props) {
  const { pending } = useFormStatus();
  return <button className={className} type="submit" disabled={pending} aria-busy={pending}>{pending ? pendingLabel : label}</button>;
}
