import { useState } from "react";
import { GlobalFilterBar } from "../components/GlobalFilterBar";
import { KpiCards } from "../components/KpiCards";
import { PartialPeriodWarning } from "../components/PartialPeriodWarning";
import { ChatPanel, ChatToggle } from "../components/ChatPanel";
import { TrendChart } from "../components/charts/TrendChart";
import { TopCategoriesChart } from "../components/charts/TopCategoriesChart";
import { RevenueByStateChart } from "../components/charts/RevenueByStateChart";
import { PaymentMixChart } from "../components/charts/PaymentMixChart";
import { DelayVsReviewChart } from "../components/charts/DelayVsReviewChart";
import { LateByStateChart } from "../components/charts/LateByStateChart";
import { ReviewDistributionChart } from "../components/charts/ReviewDistributionChart";
import { SellerConcentrationChart } from "../components/charts/SellerConcentrationChart";

export function Dashboard() {
  const [chatOpen, setChatOpen] = useState(false);

  return (
    <div className={chatOpen ? "app chat-open" : "app"}>
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">◆</span>
          <div>
            <h1>Sales Intelligence</h1>
            <p>Olist e-commerce · Brazil · currency BRL (R$)</p>
          </div>
        </div>
        <ChatToggle onClick={() => setChatOpen((o) => !o)} />
      </header>

      <div className="sticky-filters">
        <GlobalFilterBar />
        <PartialPeriodWarning />
      </div>

      <main className="content">
        <KpiCards />

        <div className="chart-grid">
          <TrendChart />
          <TopCategoriesChart />
          <RevenueByStateChart />
          <PaymentMixChart />
          <DelayVsReviewChart />
          <LateByStateChart />
          <ReviewDistributionChart />
          <SellerConcentrationChart />
        </div>

        <div className="actions">
          <button className="btn" type="button" disabled title="Phase 4">
            Summarize dashboard
          </button>
          <button className="btn-ghost" type="button" disabled title="Phase 5">
            Generate report
          </button>
          <span className="actions-note">AI summary &amp; reports arrive in Phases 4–5.</span>
        </div>
      </main>

      <ChatPanel open={chatOpen} onClose={() => setChatOpen(false)} />
    </div>
  );
}
