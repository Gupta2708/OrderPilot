import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OrderPilot | Order Supervisor",
  description: "A durable, event-driven order supervisor powered by Temporal.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
