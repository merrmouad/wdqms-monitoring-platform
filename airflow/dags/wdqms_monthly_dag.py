from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime, timedelta

default_args = {
    "owner": "mouad",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="wdqms_monthly_etl",
    default_args=default_args,
    start_date=datetime(2026, 6, 5),
    schedule="0 8 2 * *",
    catchup=False,
    tags=["wdqms", "monthly", "mysql"],
) as dag:

    run_monthly_etl = BashOperator(
        task_id="run_monthly_etl",
        bash_command="python /opt/airflow/scripts/WDQMS_Monthly_ETL.py"
    )