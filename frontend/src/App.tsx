import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Suspense, lazy, useState } from "react";
import { useAuth } from "./stores/auth";
const Landing = lazy(() => import("./pages/Landing"));
const Login = lazy(() => import("./pages/Login"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const NewEvent = lazy(() => import("./pages/NewEvent"));
const EventDetail = lazy(() => import("./pages/EventDetail"));
const Admin = lazy(() => import("./pages/Admin"));
const Settings = lazy(() => import("./pages/Settings"));

function Guard({ children, adminOnly=false }: { children: React.ReactNode; adminOnly?: boolean }) {
  const { club, loading } = useAuth();
  if (loading) return <Loader />;
  if (!club) return <Navigate to="/login" replace />;
  if (adminOnly && club.role !== "admin") return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}

function RootRedirect(){
  // Public landing for everyone; authenticated users still see landing with quick CTA
  return <Landing />;
}

function Loader(){
  return <div className="min-h-screen bg-charcoal flex items-center justify-center"><div className="flex flex-col items-center gap-3"><div className="h-8 w-8 rounded-full border-2 border-white/20 border-t-oxide animate-spin" /><p className="text-sm text-zinc-500">Loading…</p></div></div>;
}

export default function App(){
  const [qc] = useState(() => new QueryClient({
    defaultOptions: {
      queries: { staleTime: 30_000, gcTime: 5*60_000, retry: 1, refetchOnWindowFocus: false, refetchIntervalInBackground: false },
    },
  }));
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Suspense fallback={<Loader/>}>
          <Routes>
            <Route path="/" element={<RootRedirect/>} />
            <Route path="/login" element={<Login/>} />
            <Route path="/dashboard" element={<Guard><Dashboard/></Guard>} />
            <Route path="/admin" element={<Guard adminOnly><Admin/></Guard>} />
            <Route path="/events/new" element={<Guard><NewEvent/></Guard>} />
            <Route path="/events/:id" element={<Guard><EventDetail/></Guard>} />
            <Route path="/settings" element={<Guard><Settings/></Guard>} />
            <Route path="*" element={<div className="min-h-screen bg-charcoal flex items-center justify-center p-6"><div className="text-center"><h1 className="text-2xl font-bold text-white">404 — Not Found</h1><p className="text-zinc-500 mt-2">The page you’re looking for doesn’t exist.</p><a href="/dashboard" className="text-sage underline mt-4 inline-block">Go to Dashboard</a></div></div>} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
