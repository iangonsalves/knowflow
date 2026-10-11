import { authkitProxy } from "@workos-inc/authkit-nextjs";

export default authkitProxy();

export const config = {
  matcher: ["/", "/sign-in/:path*", "/sign-up/:path*", "/callback/:path*", "/workspaces/:path*"],
};
