import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";

const title = "MedMask — обезличивание медицинских PDF";
const description =
  "Безопасно удаляйте персональные данные из медицинских PDF прямо в браузере — без загрузки файлов в облако.";

export async function generateMetadata(): Promise<Metadata> {
  const incomingHeaders = await headers();
  const host = (incomingHeaders.get("x-forwarded-host") ?? incomingHeaders.get("host") ?? "127.0.0.1:8765")
    .split(",")[0]
    .trim();
  const forwardedProtocol = incomingHeaders.get("x-forwarded-proto")?.split(",")[0].trim();
  const isLocal = host.startsWith("localhost") || host.startsWith("127.0.0.1");
  const origin = `${forwardedProtocol ?? (isLocal ? "http" : "https")}://${host}`;
  const socialImage = `${origin}/og.png`;

  return {
    title,
    description,
    icons: {
      icon: "/favicon.png",
      shortcut: "/favicon.png",
    },
    openGraph: {
      title,
      description,
      type: "website",
      locale: "ru_RU",
      siteName: "MedMask",
      url: origin,
      images: [{ url: socialImage, width: 1200, height: 630, alt: "MedMask" }],
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [socialImage],
    },
  };
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru">
      <head>
        <meta name="referrer" content="no-referrer" />
        <meta
          httpEquiv="Content-Security-Policy"
          content="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' ws://127.0.0.1:* ws://localhost:*; worker-src 'self' blob:; object-src 'none'; base-uri 'self'; form-action 'none'"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
