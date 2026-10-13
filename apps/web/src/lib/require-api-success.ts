import "server-only";

import { notFound } from "next/navigation";

export function requireApiSuccess(response: Response): Response {
  if (response.status === 404) notFound();
  if (!response.ok) throw new Error("KnowFlow could not load this information. Try again shortly.");
  return response;
}
