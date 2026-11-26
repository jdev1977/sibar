import { Moon, Sun, CheckSquare } from 'lucide-react'

export default function Navbar({ dark, onToggle }) {
  return (
    <header className="sticky top-0 z-50 border-b border-slate-200 bg-white/80 backdrop-blur-md dark:border-slate-800 dark:bg-slate-950/80">
      <nav className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <a href="#" className="flex items-center gap-2 text-xl font-bold">
          <CheckSquare className="h-6 w-6 text-brand-500" /> TaskFlow
        </a>
        <div className="hidden gap-8 md:flex">
          <a href="#features" className="text-sm text-slate-600 hover:text-slate-900">Features</a>
          <a href="#pricing" className="text-sm text-slate-600 hover:text-slate-900">Pricing</a>
        </div>
        <button onClick={onToggle} aria-label="Toggle dark mode" className="rounded-lg p-2 hover:bg-slate-100 dark:hover:bg-slate-800">
          {dark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </button>
      </nav>
    </header>
  )
}
