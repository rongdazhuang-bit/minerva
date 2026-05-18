/** Kepler / escape velocity markdown sample from agent chat. */
export const KEPLER_MARKDOWN = `由机械能守恒 $\\dfrac{1}{2}mv^2 - G\\dfrac{Mm}{R} = 0$ 得：
  $$v_2 = \\sqrt{\\frac{2GM}{R}} \\quad (\\text{地球约 } 11.2 \\, \\text{km/s})$$

#### 5. 开普勒第三定律的牛顿形式
对绕同一中心天体 $M$ 运动的卫星，由向心力公式推导：
$$T^2 = \\frac{4\\pi^2}{GM} r^3 \\quad \\Rightarrow \\quad \\frac{T^2}{r^3} = \\text{常量}$$

---

### 三、适用条件与注意事项
1. **质点或球对称质量分布**：公式严格适用于质点，或质量呈球对称分布的物体（此时 $r$ 为球心距）。
2. **经典力学范围**：适用于宏观、低速、弱引力场。强引力场（如黑洞附近）或极高精度需求需用广义相对论修正。
3. **多体问题**：多个物体间引力满足叠加原理，$\\vec{F}_{\\text{合}} = \\sum \\vec{F}_i$。
4. **$r$ 的定义**：必须是两物体**质心**之间的距离，非表面间距。`
