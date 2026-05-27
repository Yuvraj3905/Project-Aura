export const metadata = {
  title: "Aura",
  description: "Autonomous B2B Solutions Architect",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
