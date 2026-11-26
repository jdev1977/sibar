import { ArrowRight, Sparkles } from 'lucide-react'
import { motion } from 'framer-motion'

export default function Hero() {
  return (
    <section className="relative overflow-hidden py-24 sm:py-32">
      <div className="absolute inset-0 -z-10 bg-gradient-to-br from-emerald-50 via-white to-teal-50 dark:from-slate-900 dark:via-slate-950 dark:to-slate-900" />
      <div className="mx-auto max-w-6xl px-6 text-center">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <span className="inline-flex items-center gap-2 rounded-full bg-brand-50 px-4 py-1.5 text-sm font-medium text-brand-600">
            <Sparkles className="h-4 w-4" /> Introducing TaskFlow 2.0
          </span>
          <h1 className="mt-8 font-display text-5xl font-bold tracking-tight sm:text-6xl">
            Manage projects <span className="text-brand-500">effortlessly</span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-slate-600 dark:text-slate-400">
            Streamline your workflow, collaborate seamlessly, and ship faster with the all-in-one platform built for modern teams.
          </p>
          <div className="mt-10 flex items-center justify-center gap-4">
            <button className="inline-flex items-center gap-2 rounded-lg bg-primary px-6 py-3 font-semibold text-primary-foreground shadow-lg hover:opacity-90">
              Get started free <ArrowRight className="h-4 w-4" />
            </button>
            <button className="rounded-lg border border-border px-6 py-3 font-semibold">Book a demo</button>
          </div>
        </motion.div>
      </div>
    </section>
  )
}
