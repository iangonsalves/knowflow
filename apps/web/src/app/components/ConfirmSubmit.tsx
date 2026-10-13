"use client";

import { useState } from "react";

type Props = { label: string; confirmation: string; danger?: boolean; className?: string };

export default function ConfirmSubmit({ label, confirmation, danger = false, className }: Props) {
  const [confirming, setConfirming] = useState(false);
  if (!confirming) {
    return <button className={className ?? `text-button${danger ? " text-danger" : ""}`} type="button" onClick={() => setConfirming(true)}>{label}</button>;
  }
  return (
    <span className="confirm-inline" role="group" aria-label={confirmation}>
      <span className="confirm-prompt">{confirmation}</span>
      <button className={`text-button${danger ? " text-danger" : ""}`} type="submit">Confirm</button>
      <button className="text-button" type="button" onClick={() => setConfirming(false)}>Cancel</button>
    </span>
  );
}
