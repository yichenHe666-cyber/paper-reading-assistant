export function Particles() {
  const particles = Array.from({ length: 20 }, (_, i) => ({
    id: i,
    colors: ['var(--neon-cyan)', 'var(--neon-magenta)', 'var(--neon-yellow)', 'var(--neon-purple)'],
    sizes: [3, 4, 5],
    durations: [15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26],
    delays: [0, 1, 2, 3, 4, 5, 6],
    lefts: [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 50],
  }))

  return (
    <div className="particles-container pointer-events-none fixed inset-0 z-0 overflow-hidden">
      {particles.map((p, i) => (
        <div
          key={p.id}
          className="particle absolute rounded-full"
          style={{
            width: p.sizes[i % p.sizes.length],
            height: p.sizes[i % p.sizes.length],
            background: p.colors[i % p.colors.length],
            left: `${p.lefts[i]}%`,
            animationDuration: `${p.durations[i % p.durations.length]}s`,
            animationDelay: `${p.delays[i % p.delays.length]}s`,
          }}
        />
      ))}
    </div>
  )
}
