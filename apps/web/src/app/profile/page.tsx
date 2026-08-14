import { redirect } from "next/navigation";

/** My criteria page removed — send bookmarks to Search. */
export default function ProfilePage() {
  redirect("/");
}
