export default function Home() {
  return (
    <main className="min-h-screen bg-slate-50 px-6 py-16 text-slate-900 sm:py-24">
      <div className="mx-auto max-w-3xl">
        <p className="text-sm font-semibold tracking-widest text-teal-700">ORDERPILOT</p>
        <h1 className="mt-6 text-4xl font-semibold tracking-tight sm:text-5xl">Order Supervisor</h1>
        <p className="mt-5 max-w-xl text-lg leading-8 text-slate-600">
          Supervise an order from creation to completion, with durable orchestration and an auditable history.
        </p>
        <section aria-labelledby="foundation" className="mt-10 rounded-2xl border border-slate-200 bg-white p-6 sm:p-8">
          <p className="text-xs font-semibold uppercase tracking-wider text-teal-700">Stage 0</p>
          <h2 id="foundation" className="mt-2 text-xl font-semibold">Application foundation</h2>
          <p className="mt-3 leading-7 text-slate-600">
            The application scaffold is in place. Order runs and supervisor controls will arrive in later stages.
          </p>
        </section>
      </div>
    </main>
  );
}
