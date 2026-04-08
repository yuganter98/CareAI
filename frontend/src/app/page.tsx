import { redirect } from "next/navigation";

export default function Home() {
  // Immediately redirect root traffic to the login natively avoiding hydration
  redirect("/login");
}
