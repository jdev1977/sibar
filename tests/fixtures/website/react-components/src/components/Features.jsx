import { Zap, Shield, Users, BarChart3, Clock, Layers } from 'lucide-react'

const features = [
  { icon: Zap, title: 'Lightning Fast', description: 'Built for speed with real-time sync across all your devices.' },
  { icon: Shield, title: 'Secure by Default', description: 'Enterprise-grade security with end-to-end encryption.' },
  { icon: Users, title: 'Team Collaboration', description: 'Work together seamlessly with your entire team.' },
  { icon: BarChart3, title: 'Powerful Analytics', description: 'Gain insights into your team productivity.' },
  { icon: Clock, title: 'Time Tracking', description: 'Track time spent on tasks automatically.' },
  { icon: Layers, title: 'Integrations', description: 'Connect with 100+ tools you already use.' },
]

export default function Features() {
  return (
    <section id="features" className="py-24 bg-slate-50 dark:bg-slate-900">
      <div className="mx-auto max-w-6xl px-6">
        <h2 className="text-center text-3xl font-bold sm:text-4xl">Everything you need to stay productive</h2>
        <div className="mt-16 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((feature) => (
            <div key={feature.title} className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm transition hover:shadow-md dark:border-slate-800 dark:bg-slate-950">
              <div className="mb-4 inline-flex rounded-lg bg-brand-50 p-3 text-brand-600">
                <feature.icon className="h-6 w-6" />
              </div>
              <h3 className="text-lg font-semibold">{feature.title}</h3>
              <p className="mt-2 text-slate-600 dark:text-slate-400">{feature.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
