/** User-reported DFT derivation markdown (mixed CJK, lists, inline/display math). */
export const DFT_DERIVATION_MARKDOWN = `#### 3.2 推导思路（连续信号的采样与截断）

DFT 的推导可以看作是对连续傅里叶变换（FT）进行**离散化**和**有限化**的结果。

1.  **时域采样**：将连续信号 $f(t)$ 乘以采样冲激串，时域相乘对应频域周期延拓。
2.  **时域截断**（加窗）：取有限长度 $N$ 的数据，对应频域与 Sinc 函数卷积（产生频谱泄露）。
3.  **频域采样**：为了在计算机中存储，频域也必须是离散的。根据频域采样定理，频域的离散化会导致时域的周期延拓。

**代数推导思路（更直观）：**
假设我们只关心傅里叶级数在基频 $\\omega_0 = \\frac{2\\pi}{NT}$（$T$为采样间隔）的整数倍上的频率分量。
将连续傅里叶变换的积分近似为黎曼和（积分变求和，$dt \\to T$）：

$$F(k\\omega_0) \\approx \\sum_{n=0}^{N-1} f(nT) e^{-i k \\omega_0 nT} \\cdot T$$

忽略常数比例因子 $T$（通常归一化处理），令 $x[n] = f(nT)$，$\\omega_0 = \\frac{2\\pi}{N}$（假设 $T=1$），即得到 DFT 公式。`
