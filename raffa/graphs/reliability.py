import numpy as np
import matplotlib.pyplot as plt

# Definindo o intervalo de tempo (t)
t = np.linspace(0, 5, 500)

z = 1.0
y = np.exp(-z * t)

plt.figure(figsize=(10, 6))
plt.plot(t, y, label=f'z = {z}')
# plt.title('Gráfico de $e^{-zt}$ para $z = 1$')
plt.xlabel('Tempo (t)')
plt.ylabel('$e^{-zt}$')
plt.grid(True, linestyle='--', alpha=0.7)
plt.legend()
plt.axhline(0, color='black', linewidth=1)
plt.axvline(0, color='black', linewidth=1)
plt.show()
