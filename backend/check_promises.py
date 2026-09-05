from app.services.promise_tracker import check_and_expire_promises

if __name__ == "__main__":
    print("Checking and expiring overdue promises...")
    count = check_and_expire_promises()
    print(f"Done. Expired {count} promise(s).")
