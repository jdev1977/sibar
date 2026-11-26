import React from 'react';
const links = ['Home','About'];
const faqs = [{q:'a',a:'b'}];
export default function App(){
  const names = links.map(l => l.toUpperCase()).join(', ');
  return (<div className="min-h-screen bg-white">
    <nav className="flex">{links.map((l) => <a key={l} href="#">{l}</a>)}</nav>
    <section className="py-20"><h1>Hello {names}</h1><div className="flex"><p className="lead">Intro</p></div></section>
    <section className="py-20"><h2>FAQ</h2>
      {faqs.map((f) => (
        <div key={f.q} className="border-b py-4"><h3>{f.q}</h3><p>{f.a}</p></div>
      ))}
    </section>
  </div>);
}
