from __future__ import annotations
import copy, importlib.util, json
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
SPEC=importlib.util.spec_from_file_location("ssc", ROOT/"scripts/solar_storage_charging_model.py")
M=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(M)
T=json.loads((ROOT/"templates/project-input.json").read_text())
N=0

def check(name, fn):
 global N
 fn(); N+=1; print("PASS",name)

def close(a,b,tol=1e-6):
 assert abs(a-b)<=tol*max(1,abs(a),abs(b)),(a,b)

def test_energy_balance():
 r=M.run_model(copy.deepcopy(T))["base"]
 for x in r["rows"]:
  close(x["pv_generation_kwh"],x["pv_direct_kwh"]+x["pv_to_storage_kwh"]+x["pv_export_kwh"])
  close(x["storage_discharge_kwh"],(x["pv_to_storage_kwh"]+x["grid_to_storage_kwh"])*x["storage_roundtrip_efficiency"])
  close(x["charging_energy_kwh"],x["pv_direct_kwh"]+x["storage_discharge_kwh"]+x["grid_direct_kwh"])
  close(x["energy_balance_error_kwh"],0)

def test_no_duplicate_internal_revenue():
 r=M.run_model(copy.deepcopy(T))["base"]["rows"][0]
 assert "pv_self_use_revenue" not in r and "storage_arbitrage_revenue" not in r
 close(r["total_revenue"],r["charging_energy_revenue"]+r["service_fee_revenue"]+r["pv_export_revenue"]+r["ancillary_revenue"])

def test_unverified_ancillary_excluded():
 c=copy.deepcopy(T); c["ancillary"]["annual_revenue"]=999999; c["ancillary"]["verified"]=False
 r=M.run_model(c)
 assert "UNVERIFIED_ANCILLARY_REVENUE" in r["hard_flags"]
 close(r["base"]["rows"][0]["ancillary_revenue"],0)

def test_verified_ancillary_included():
 c=copy.deepcopy(T); c["ancillary"].update({"annual_revenue":100000,"verified":True})
 r=M.run_model(c); close(r["base"]["rows"][0]["ancillary_revenue"],100000)

def test_capacity_limit_flag():
 c=copy.deepcopy(T); c["charging"]["base_daily_kwh_per_stall"]=5000
 r=M.run_model(c)
 assert "CHARGING_CAPACITY_EXCEEDED" in r["hard_flags"]
 assert r["base"]["rows"][0]["charging_energy_kwh"]<=r["base"]["rows"][0]["charging_capacity_limit_kwh"]

def test_storage_is_demand_constrained():
 c=copy.deepcopy(T); c["charging"]["base_daily_kwh_per_stall"]=1
 r=M.run_model(c)["base"]["rows"][0]
 assert r["storage_discharge_kwh"]<=r["charging_energy_kwh"]

def test_no_storage_counterfactual():
 r=M.run_model(copy.deepcopy(T))
 assert r["no_storage"]["rows"][0]["storage_discharge_kwh"]==0
 assert r["base"]["rows"][0]["grid_direct_kwh"]<r["no_storage"]["rows"][0]["grid_direct_kwh"]

def test_replacement_capex():
 r=M.run_model(copy.deepcopy(T))["base"]
 close(r["rows"][7]["replacement_capex"],300000); close(r["rows"][9]["replacement_capex"],700000)

def test_project_and_equity_separated():
 r=M.run_model(copy.deepcopy(T))["base"]
 close(r["project_cashflows"][0],-T["project"]["total_capex"])
 close(r["equity_cashflows"][0],-T["project"]["total_capex"]*(1-T["debt"]["debt_ratio"]))
 assert r["project_cashflows"]!=r["equity_cashflows"]

def test_debt_repaid():
 r=M.run_model(copy.deepcopy(T))["base"]
 close(r["rows"][T["debt"]["tenor_years"]-1]["closing_debt"],0)

def test_p90_not_better_than_base():
 r=M.run_model(copy.deepcopy(T)); assert r["p90"]["metrics"]["project_npv"]<=r["base"]["metrics"]["project_npv"]

def test_invalid_array_rejected():
 c=copy.deepcopy(T); c["charging"]["demand_multiplier_by_year"]=[1,2]
 try: M.run_model(c); raise AssertionError("expected ValueError")
 except ValueError: pass

def test_site_term_gate():
 c=copy.deepcopy(T); c["project"]["site_term_years"]=5
 r=M.run_model(c); assert "SITE_TERM_SHORTER_THAN_FINANCING" in r["hard_flags"]

if __name__=="__main__":
 for n,f in list(globals().items()):
  if n.startswith("test_"): check(n,f)
 print(f"PASS total={N}")
