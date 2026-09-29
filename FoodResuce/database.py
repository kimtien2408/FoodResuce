import pyodbc

CONNECTION_STRING = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=.\\SQLEXPRESS;"
    "DATABASE=FoodRescueDB;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)


def get_connection():
    return pyodbc.connect(CONNECTION_STRING)


def check_login(email, password):
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT UserId, FullName, Role 
        FROM Users 
        WHERE Email = ? AND Password = ? AND IsActive = 1
    """
    cursor.execute(query, (email, password))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"user_id": row[0], "full_name": row[1], "role": row[2]}
    return None


def register_user(full_name, email, password, phone_number, role):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT 1 FROM Users WHERE Email = ?", (email,))
    if cursor.fetchone():
        conn.close()
        return False

    query = """
        INSERT INTO Users (FullName, Email, Password, PhoneNumber, Role)
        VALUES (?, ?, ?, ?, ?)
    """
    cursor.execute(query, (full_name, email, password, phone_number, role))
    conn.commit()
    conn.close()
    return True


def get_user_profile(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT FullName, Email, PhoneNumber, Role
        FROM Users
        WHERE UserId = ? AND IsActive = 1
        """,
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return dict(zip(["FullName", "Email", "PhoneNumber", "Role"], row))


def update_user_profile(user_id, full_name, email, phone_number,
                        current_password, new_password):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT Password FROM Users WHERE UserId = ? AND IsActive = 1",
            (user_id,),
        )
        user = cursor.fetchone()
        if not user:
            return "not_found"

        cursor.execute(
            "SELECT 1 FROM Users WHERE Email = ? AND UserId <> ?",
            (email, user_id),
        )
        if cursor.fetchone():
            return "email_exists"

        if new_password:
            if user[0] != current_password:
                return "wrong_password"
            cursor.execute(
                """
                UPDATE Users
                SET FullName = ?, Email = ?, PhoneNumber = ?, Password = ?
                WHERE UserId = ? AND IsActive = 1
                """,
                (full_name, email, phone_number, new_password, user_id),
            )
        else:
            cursor.execute(
                """
                UPDATE Users
                SET FullName = ?, Email = ?, PhoneNumber = ?
                WHERE UserId = ? AND IsActive = 1
                """,
                (full_name, email, phone_number, user_id),
            )
        conn.commit()
        return "updated"
    except pyodbc.IntegrityError:
        conn.rollback()
        return "email_exists"
    finally:
        conn.close()


def get_active_batches():
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT b.BatchId, b.FoodName, b.OriginalPrice, b.RescuePrice, 
               b.AvailableQuantity, CONVERT(VARCHAR(5), b.PickupStartTime, 108) AS PickupStartTime,
               CONVERT(VARCHAR(5), b.PickupEndTime, 108) AS PickupEndTime,
               b.ImageUrl, s.StoreName, s.PhoneNumber AS StorePhone, s.Address
        FROM DailyBatches b
        JOIN Stores s ON b.StoreId = s.StoreId
        WHERE b.Status = N'Active' AND b.AvailableQuantity > 0
    """
    cursor.execute(query)
    columns = [col[0] for col in cursor.description]
    results = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return results


def get_cart_batches(batch_ids):
    batch_ids = list(dict.fromkeys(int(batch_id) for batch_id in batch_ids))
    if not batch_ids:
        return []

    placeholders = ", ".join("?" for _ in batch_ids)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        f"""
        SELECT b.BatchId, b.FoodName, b.ImageUrl, b.RescuePrice,
               b.AvailableQuantity, b.PickupStartTime, b.PickupEndTime,
               b.Status, s.StoreName, s.Address
        FROM DailyBatches b
        JOIN Stores s ON s.StoreId = b.StoreId
        WHERE b.BatchId IN ({placeholders})
        """,
        tuple(batch_ids),
    )
    columns = [column[0] for column in cursor.description]
    results = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return results


def get_store_for_owner(owner_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT StoreId, StoreName, PhoneNumber, Address, ClosingTime
        FROM Stores
        WHERE OwnerId = ?
        """,
        (owner_id,),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return dict(zip(["StoreId", "StoreName", "PhoneNumber", "Address", "ClosingTime"], row))


def create_store(owner_id, store_name, phone_number, address, closing_time):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO Stores (OwnerId, StoreName, PhoneNumber, Address, ClosingTime)
        VALUES (?, ?, ?, ?, ?)
        """,
        (owner_id, store_name, phone_number, address, closing_time),
    )
    conn.commit()
    conn.close()


def get_shop_batches(owner_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT b.BatchId, b.FoodName, b.ImageUrl, b.OriginalPrice, b.RescuePrice,
               b.AvailableQuantity, b.PickupStartTime, b.PickupEndTime, b.Status,
               s.StoreName,
               CASE WHEN EXISTS (
                   SELECT 1 FROM Orders o WHERE o.BatchId = b.BatchId
               ) THEN 1 ELSE 0 END AS HasOrders
        FROM DailyBatches b
        JOIN Stores s ON s.StoreId = b.StoreId
        WHERE s.OwnerId = ? AND b.Status <> N'Inactive'
        ORDER BY b.BatchId DESC
        """,
        (owner_id,),
    )
    columns = [column[0] for column in cursor.description]
    results = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return results


def get_shop_batch(owner_id, batch_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT b.BatchId, b.FoodName, b.ImageUrl, b.OriginalPrice, b.RescuePrice,
               b.AvailableQuantity, b.PickupStartTime, b.PickupEndTime, b.Status,
               s.StoreName,
               CASE WHEN EXISTS (
                   SELECT 1 FROM Orders o WHERE o.BatchId = b.BatchId
               ) THEN 1 ELSE 0 END AS HasOrders
        FROM DailyBatches b
        JOIN Stores s ON s.StoreId = b.StoreId
        WHERE b.BatchId = ? AND s.OwnerId = ?
        """,
        (batch_id, owner_id),
    )
    row = cursor.fetchone()
    columns = [column[0] for column in cursor.description]
    conn.close()
    return dict(zip(columns, row)) if row else None


def get_shop_orders(owner_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT o.OrderId, o.Quantity, o.TotalPrice, o.OrderStatus, o.CreatedAt,
               b.FoodName, u.FullName AS CustomerName, u.PhoneNumber AS CustomerPhone
        FROM Orders o
        JOIN DailyBatches b ON b.BatchId = o.BatchId
        JOIN Stores s ON s.StoreId = b.StoreId
        JOIN Users u ON u.UserId = o.CustomerId
        WHERE s.OwnerId = ?
        ORDER BY o.CreatedAt DESC
        """,
        (owner_id,),
    )
    columns = [column[0] for column in cursor.description]
    results = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return results


def create_shop_batch(owner_id, food_name, image_url, original_price, rescue_price,
                      available_quantity, pickup_start_time, pickup_end_time):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO DailyBatches
            (StoreId, FoodName, ImageUrl, OriginalPrice, RescuePrice,
             AvailableQuantity, PickupStartTime, PickupEndTime, Status)
        SELECT StoreId, ?, ?, ?, ?, ?, ?, ?, N'Active'
        FROM Stores
        WHERE OwnerId = ?
        """,
        (food_name, image_url, original_price, rescue_price, available_quantity,
         pickup_start_time, pickup_end_time, owner_id),
    )
    inserted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return inserted


def update_shop_batch(owner_id, batch_id, food_name, image_url, original_price,
                      rescue_price, available_quantity, pickup_start_time, pickup_end_time):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE b
        SET FoodName = ?, ImageUrl = ?, OriginalPrice = ?, RescuePrice = ?,
            AvailableQuantity = ?, PickupStartTime = ?, PickupEndTime = ?
        FROM DailyBatches b
        JOIN Stores s ON s.StoreId = b.StoreId
        WHERE b.BatchId = ? AND s.OwnerId = ?
        """,
        (food_name, image_url, original_price, rescue_price, available_quantity,
         pickup_start_time, pickup_end_time, batch_id, owner_id),
    )
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def delete_shop_batch(owner_id, batch_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            DELETE b
            FROM DailyBatches b
            JOIN Stores s ON s.StoreId = b.StoreId
            WHERE b.BatchId = ? AND s.OwnerId = ?
              AND NOT EXISTS (
                  SELECT 1 FROM Orders o WHERE o.BatchId = b.BatchId
              )
            """,
            (batch_id, owner_id),
        )
        deleted = cursor.rowcount > 0
        conn.commit()
    except pyodbc.IntegrityError:
        conn.rollback()
        deleted = False
    finally:
        conn.close()
    return deleted


def create_rescue_order(customer_id, batch_id, quantity):
    conn = get_connection()
    cursor = conn.cursor()
    sql = """
        SET NOCOUNT ON;
        DECLARE @OrderId INT, @StatusCode INT;
        EXEC sp_CreateRescueOrder 
            @CustomerId = ?, 
            @BatchId = ?, 
            @Quantity = ?, 
            @OrderId = @OrderId OUTPUT, 
            @StatusCode = @StatusCode OUTPUT;
        SELECT @OrderId AS OrderId, @StatusCode AS StatusCode;
    """
    cursor.execute(sql, (customer_id, batch_id, quantity))
    res = cursor.fetchone()
    conn.commit()
    conn.close()

    return {"order_id": res[0], "status_code": res[1]}