import { Check } from 'lucide-react'

const plans = [
  { name: 'Free', price: '$0', features: ['Up to 3 projects', 'Basic analytics'], highlighted: false },
  { name: 'Pro', price: '$12', features: ['Unlimited projects', 'Advanced analytics', 'Priority support'], highlighted: true },
  { name: 'Team', price: '$49', features: ['Everything in Pro', 'SSO', 'Admin controls'], highlighted: false },
]

export default function Pricing() {
  return (
    <section id="pricing" className="py-24">
      <div className="mx-auto max-w-6xl px-6">
        <h2 className="text-center text-3xl font-bold">Simple, transparent pricing</h2>
        <div className="mt-16 grid gap-8 md:grid-cols-3">
          {plans.map((plan) => (
            <div key={plan.name} className={`rounded-2xl p-8 ${plan.highlighted ? 'bg-brand-600 text-white ring-4 ring-brand-500/30 scale-105' : 'border border-slate-200 dark:border-slate-800'}`}>
              <h3 className="text-lg font-semibold">{plan.name}</h3>
              <p className="mt-4 text-4xl font-bold">{plan.price}<span className="text-base font-normal">/month</span></p>
              <ul className="mt-8 space-y-3">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-center gap-2"><Check className="h-4 w-4" /> {f}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
