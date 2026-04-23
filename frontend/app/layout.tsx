import "./globals.css";

export const metadata = {
  title: "Zenith Roster Analyzer",
  description: "AI-powered staff rostering for hospitality operations",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}