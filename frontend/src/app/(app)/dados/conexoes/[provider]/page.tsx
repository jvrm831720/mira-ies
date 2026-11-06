import { notFound } from "next/navigation";
import { NativeConnectionDetail } from "@/components/data-hub/native-connection-detail";

export default async function DataHubConnectionPage({params}: {params: Promise<{provider:string}>}) {
  const { provider } = await params;
  if (provider !== "jacad" && provider !== "sponte") notFound();
  return <NativeConnectionDetail provider={provider} />;
}
