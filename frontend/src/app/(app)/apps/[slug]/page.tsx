import { AppDetailExperience } from "@/components/apps/app-detail-experience";

export default async function AppDetailsPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <AppDetailExperience slug={slug} />;
}
