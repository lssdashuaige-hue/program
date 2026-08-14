import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { safeNextPath } from "@/lib/safe-next-path";

function privateRedirect(destination: URL): NextResponse {
  const response = NextResponse.redirect(destination);
  response.headers.set(
    "Cache-Control",
    "private, no-cache, no-store, must-revalidate, max-age=0",
  );
  response.headers.set("Expires", "0");
  response.headers.set("Pragma", "no-cache");
  return response;
}

export async function GET(request: Request) {
  const requestUrl = new URL(request.url);
  const code = requestUrl.searchParams.get("code");
  const nextPath = safeNextPath(requestUrl.searchParams.get("next"));

  if (code) {
    const supabase = await createClient();
    const { error } = await supabase.auth.exchangeCodeForSession(code);

    if (!error) {
      const destination = new URL(nextPath, requestUrl.origin);
      if (destination.origin === requestUrl.origin) {
        return privateRedirect(destination);
      }
    }
  }

  const errorUrl = new URL("/auth", requestUrl.origin);
  errorUrl.searchParams.set("error", "callback");
  errorUrl.searchParams.set("next", nextPath);
  return privateRedirect(errorUrl);
}
