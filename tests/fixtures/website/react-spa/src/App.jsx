import { useState } from 'react';
import { Activity, Users, Settings } from 'lucide-react';
import { LineChart, Line } from 'recharts';

const stats = [
  { label: 'Active users', value: '10,000+' },
  { label: 'Revenue', value: '$48k' },
  { label: 'Uptime', value: '99.9%' },
];

function StatCard({ label, value }) {
  return (
    <div className="rounded-xl bg-slate-900 p-6 shadow-md shadow-violet-500/20">
      <p className="text-sm text-slate-400">{label}</p>
      <p className="mt-2 text-3xl font-semibold">{value}</p>
    </div>
  );
}

export default function App() {
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans">
      <Navbar onMenu={() => setOpen(!open)} />
      <Hero />
      <main className="mx-auto max-w-6xl px-4">
        <section className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {stats.map((s) => (
            <StatCard key={s.label} label={s.label} value={s.value} />
          ))}
        </section>
        <section className="mt-10 rounded-xl bg-slate-900 p-6">
          <h2 className="text-xl font-semibold">Unlock deeper insights 📈</h2>
          <LineChart width={400} height={200} data={[]}><Line dataKey="v" /></LineChart>
        </section>
      </main>
      <Footer />
    </div>
  );
}

function Navbar({ onMenu }) {
  return (
    <nav className="flex items-center justify-between px-6 py-4">
      <span className="font-bold">Pulse</span>
      <button onClick={onMenu} aria-label="Open menu"><Settings size={20} /></button>
    </nav>
  );
}

function Hero() {
  return (
    <header className="px-6 py-16 text-center">
      <h1 className="text-4xl font-bold bg-gradient-to-r from-violet-400 to-cyan-400 bg-clip-text text-transparent">Your metrics, at a glance</h1>
      <p className="mt-4 text-slate-400">Track what matters — in real time.</p>
    </header>
  );
}

function Footer() {
  return <footer className="py-8 text-center text-slate-500">Built with care</footer>;
}
