import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "Fantasy Mock Draft",
  description: "ESPN-style mock draft room with probabilistic CPU picks"
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>
        {children}
      </body>
    </html>
  );
}

