import os
from uuid import uuid4

from database import (
    check_login,
    create_rescue_order,
    create_shop_batch,
    create_store,
    delete_shop_batch,
    get_active_batches,
    get_cart_batches,
    get_shop_batches,
    get_shop_batch,
    get_shop_orders,
    get_store_for_owner,
    get_user_profile,
    register_user,
    update_user_profile,
    update_shop_batch,
)
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "food_rescue_secret_key"
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def save_uploaded_image(uploaded_file, current_image=""):
    if not uploaded_file or not uploaded_file.filename:
        return current_image

    safe_name = secure_filename(uploaded_file.filename)
    extension = os.path.splitext(safe_name)[1].lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Định dạng ảnh không được hỗ trợ.")

    upload_folder = os.path.join(app.static_folder, "uploads")
    os.makedirs(upload_folder, exist_ok=True)
    filename = f"{uuid4().hex}{extension}"
    uploaded_file.save(os.path.join(upload_folder, filename))
    return f"/static/uploads/{filename}"


def customer_required():
    if session.get("role") == "Customer" and session.get("user_id"):
        return True
    flash("Chức năng này chỉ dành cho khách hàng.", "danger")
    return False


def redirect_for_current_role():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    if session.get("role") == "ShopOwner":
        return redirect(url_for("shop_dashboard"))
    return redirect(url_for("index"))


def get_customer_cart():
    user_id = session.get("user_id")
    if session.get("cart_user_id") != user_id:
        session["cart_user_id"] = user_id
        session["cart"] = {}
    raw_cart = session.get("cart", {})
    if not isinstance(raw_cart, dict):
        raw_cart = {}
    cart = {}
    for batch_id, quantity in raw_cart.items():
        try:
            batch_id = str(int(batch_id))
            quantity = int(quantity)
        except (TypeError, ValueError):
            continue
        if quantity > 0:
            cart[batch_id] = quantity
    session["cart"] = cart
    return cart


@app.route("/")
def index():
    batches = get_active_batches()
    cart_count = sum(get_customer_cart().values()) if session.get("role") == "Customer" else 0
    return render_template("index.html", batches=batches, cart_count=cart_count)


@app.route("/customer/shop")
def customer_shop():
        if not customer_required():
                return redirect_for_current_role()
        batches = get_active_batches()
        cart_count = sum(get_customer_cart().values())
        return render_template("index.html", batches=batches, cart_count=cart_count)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = check_login(request.form.get("email"), request.form.get("password"))
        if user:
            session["user_id"] = user["user_id"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"]
            flash(f"Xin chào {user['full_name']}!", "success")
            if user["role"] == "ShopOwner":
                return redirect(url_for("shop_dashboard"))
            if user["role"] == "Customer":
                session["cart"] = {}
                session["cart_user_id"] = user["user_id"]
                return redirect(url_for("customer_shop"))
            return redirect(url_for("index"))
        flash("Email hoặc mật khẩu không chính xác.", "danger")
    return render_template("account/login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Bạn đã đăng xuất.", "success")
    return redirect(url_for("index"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        phone_number = request.form.get("phone_number", "").strip()
        role = request.form.get("role", "Customer")

        if role not in {"Customer", "ShopOwner"}:
            flash("Vai trò đăng ký không hợp lệ.", "danger")
            return render_template("account/register.html")

        if register_user(full_name, email, password, phone_number, role):
            flash("Đăng ký thành công. Bạn có thể đăng nhập ngay.", "success")
            return redirect(url_for("login"))
        flash("Email này đã được sử dụng.", "danger")
    return render_template("account/register.html")


@app.route("/account/profile", methods=["GET", "POST"])
def account_profile():
    user_id = session.get("user_id")
    if not user_id:
        flash("Vui lòng đăng nhập để chỉnh sửa hồ sơ.", "danger")
        return redirect(url_for("login"))

    profile = get_user_profile(user_id)
    if not profile:
        session.clear()
        flash("Không tìm thấy tài khoản đang hoạt động.", "danger")
        return redirect(url_for("login"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        phone_number = request.form.get("phone_number", "").strip()
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        form_profile = {
            "FullName": full_name,
            "Email": email,
            "PhoneNumber": phone_number,
            "Role": profile["Role"],
        }

        if (not full_name or len(full_name) > 100 or not email or "@" not in email
                or len(email) > 100 or not phone_number or len(phone_number) > 15):
            flash("Vui lòng kiểm tra họ tên, email và số điện thoại.", "danger")
            return render_template("account/profile.html", profile=form_profile)

        if new_password and (len(new_password) < 8 or len(new_password) > 255):
            flash("Mật khẩu mới phải có từ 8 đến 255 ký tự.", "danger")
            return render_template("account/profile.html", profile=form_profile)
        if new_password != confirm_password:
            flash("Mật khẩu mới nhập lại không khớp.", "danger")
            return render_template("account/profile.html", profile=form_profile)

        result = update_user_profile(
            user_id, full_name, email, phone_number, current_password, new_password
        )
        if result == "updated":
            session["full_name"] = full_name
            flash("Thông tin cá nhân đã được cập nhật.", "success")
            return redirect(url_for("account_profile"))
        if result == "email_exists":
            flash("Email này đã được sử dụng bởi tài khoản khác.", "danger")
        elif result == "wrong_password":
            flash("Mật khẩu hiện tại không chính xác.", "danger")
        else:
            flash("Không thể cập nhật tài khoản này.", "danger")
        return render_template("account/profile.html", profile=form_profile)

    return render_template("account/profile.html", profile=profile)


def shop_owner_required():
    if session.get("role") != "ShopOwner":
        flash("Bạn cần đăng nhập bằng tài khoản chủ cửa hàng.", "danger")
        return False
    return True


@app.route("/shop/dashboard")
def shop_dashboard():
    if not shop_owner_required():
        return redirect(url_for("login"))

    owner_id = session["user_id"]
    store = get_store_for_owner(owner_id)
    batches = get_shop_batches(owner_id) if store else []
    return render_template("DailyBatches/list.html", store=store, batches=batches)


@app.route("/shop/orders")
def shop_orders():
    if not shop_owner_required():
        return redirect(url_for("login"))

    owner_id = session["user_id"]
    store = get_store_for_owner(owner_id)
    orders = get_shop_orders(owner_id) if store else []
    return render_template("Order/shop.html", store=store, orders=orders)


@app.route("/shop/store", methods=["POST"])
def save_shop_store():
    if not shop_owner_required():
        return redirect(url_for("login"))

    create_store(
        session["user_id"],
        request.form.get("store_name", "").strip(),
        request.form.get("phone_number", "").strip(),
        request.form.get("address", "").strip(),
        request.form.get("closing_time"),
    )
    flash("Đã tạo thông tin cửa hàng.", "success")
    return redirect(url_for("shop_dashboard"))


@app.route("/shop/products/add")
def add_shop_product():
    if not shop_owner_required():
        return redirect(url_for("login"))
    return render_template("DailyBatches/add.html")


@app.route("/shop/products/<int:batch_id>")
def show_shop_product(batch_id):
    if not shop_owner_required():
        return redirect(url_for("login"))
    batch = get_shop_batch(session["user_id"], batch_id)
    if not batch:
        flash("Không tìm thấy sản phẩm của bạn.", "danger")
        return redirect(url_for("shop_dashboard"))
    return render_template("DailyBatches/show.html", batch=batch)


@app.route("/shop/products/<int:batch_id>/edit")
def edit_shop_product(batch_id):
    if not shop_owner_required():
        return redirect(url_for("login"))
    batch = get_shop_batch(session["user_id"], batch_id)
    if not batch:
        flash("Không tìm thấy sản phẩm của bạn.", "danger")
        return redirect(url_for("shop_dashboard"))
    return render_template("DailyBatches/edit.html", batch=batch)


@app.route("/shop/products/save", methods=["POST"])
def save_shop_product():
    if not shop_owner_required():
        return redirect(url_for("login"))

    try:
        image_path = save_uploaded_image(
            request.files.get("image"),
            request.form.get("current_image", "").strip(),
        )
    except ValueError as error:
        flash(str(error), "danger")
        return redirect(url_for("shop_dashboard"))

    form_values = (
        request.form.get("food_name", "").strip(),
        image_path,
        request.form.get("original_price"),
        request.form.get("rescue_price"),
        request.form.get("available_quantity"),
        request.form.get("pickup_start_time"),
        request.form.get("pickup_end_time"),
    )
    batch_id = request.form.get("batch_id")
    if batch_id:
        updated = update_shop_batch(session["user_id"], int(batch_id), *form_values)
        flash("Đã cập nhật sản phẩm." if updated else "Không tìm thấy sản phẩm của bạn.", "success" if updated else "danger")
    else:
        created = create_shop_batch(session["user_id"], *form_values)
        flash("Đã thêm sản phẩm mới." if created else "Chưa tạo được sản phẩm. Hãy kiểm tra cửa hàng của bạn.", "success" if created else "danger")
    return redirect(url_for("shop_dashboard"))


@app.route("/shop/products/<int:batch_id>/delete", methods=["GET", "POST"])
def delete_shop_product(batch_id):
    if not shop_owner_required():
        return redirect(url_for("login"))

    owner_id = session["user_id"]
    batch = get_shop_batch(owner_id, batch_id)
    if not batch:
        flash("Không tìm thấy sản phẩm của bạn.", "danger")
        return redirect(url_for("shop_dashboard"))

    if request.method == "GET":
        return render_template("DailyBatches/delete.html", batch=batch)

    deleted = delete_shop_batch(owner_id, batch_id)
    flash(
        "Đã xóa sản phẩm." if deleted else "Không thể xóa sản phẩm đã phát sinh đơn hàng.",
        "success" if deleted else "danger",
    )
    return redirect(url_for("shop_dashboard"))


@app.route("/cart/add", methods=["POST"])
@app.route("/order", methods=["POST"])
def add_to_cart():
    if not customer_required():
        return redirect_for_current_role()

    try:
        batch_id = int(request.form.get("batch_id", ""))
        quantity = int(request.form.get("quantity", "1"))
    except (TypeError, ValueError):
        flash("Sản phẩm hoặc số lượng không hợp lệ.", "danger")
        return redirect(url_for("customer_shop"))

    products = get_cart_batches([batch_id])
    if not products or products[0]["Status"] != "Active":
        flash("Sản phẩm không còn khả dụng.", "danger")
        return redirect(url_for("customer_shop"))

    cart = get_customer_cart()
    cart_key = str(batch_id)
    requested_total = cart.get(cart_key, 0) + quantity
    if quantity < 1 or requested_total > products[0]["AvailableQuantity"]:
        flash("Số lượng vượt quá tồn kho hiện tại.", "danger")
        return redirect(url_for("customer_shop"))

    cart[cart_key] = requested_total
    session["cart"] = cart
    flash("Đã thêm sản phẩm vào giỏ hàng.", "success")
    return redirect(url_for("customer_shop"))


@app.route("/cart")
def view_cart():
    if not customer_required():
        return redirect_for_current_role()

    cart = get_customer_cart()
    products = get_cart_batches(cart.keys())
    products_by_id = {str(product["BatchId"]): product for product in products}
    cart_items = []
    for batch_id, quantity in list(cart.items()):
        product = products_by_id.get(batch_id)
        if not product:
            continue
        can_checkout = (
            product["Status"] == "Active"
            and quantity <= product["AvailableQuantity"]
        )
        cart_items.append({
            **product,
            "Quantity": quantity,
            "LineTotal": product["RescuePrice"] * quantity,
            "CanCheckout": can_checkout,
        })

    found_ids = set(products_by_id)
    for batch_id in list(cart):
        if batch_id not in found_ids:
            cart.pop(batch_id)
    session["cart"] = cart
    return render_template(
        "Cart/index.html",
        cart_items=cart_items,
        total=sum(item["LineTotal"] for item in cart_items),
        cart_ready=bool(cart_items) and all(item["CanCheckout"] for item in cart_items),
        cart_count=sum(cart.values()),
    )


@app.route("/cart/update/<int:batch_id>", methods=["POST"])
def update_cart_item(batch_id):
    if not customer_required():
        return redirect_for_current_role()

    cart = get_customer_cart()
    cart_key = str(batch_id)
    if cart_key not in cart:
        flash("Sản phẩm không có trong giỏ hàng.", "danger")
        return redirect(url_for("view_cart"))

    try:
        quantity = int(request.form.get("quantity", ""))
    except (TypeError, ValueError):
        quantity = 0

    products = get_cart_batches([batch_id])
    if (quantity < 1 or not products or products[0]["Status"] != "Active"
            or quantity > products[0]["AvailableQuantity"]):
        flash("Số lượng không hợp lệ hoặc vượt quá tồn kho.", "danger")
        return redirect(url_for("view_cart"))

    cart[cart_key] = quantity
    session["cart"] = cart
    flash("Đã cập nhật số lượng trong giỏ.", "success")
    return redirect(url_for("view_cart"))


@app.route("/cart/remove/<int:batch_id>", methods=["POST"])
def remove_cart_item(batch_id):
    if not customer_required():
        return redirect_for_current_role()
    cart = get_customer_cart()
    cart.pop(str(batch_id), None)
    session["cart"] = cart
    flash("Đã xóa sản phẩm khỏi giỏ hàng.", "success")
    return redirect(url_for("view_cart"))


@app.route("/cart/checkout", methods=["POST"])
def checkout_cart():
    if not customer_required():
        return redirect_for_current_role()

    cart = get_customer_cart()
    products = get_cart_batches(cart.keys())
    products_by_id = {str(product["BatchId"]): product for product in products}
    created_orders = []
    failed_items = []

    for batch_id, quantity in list(cart.items()):
        product = products_by_id.get(batch_id)
        if (not product or product["Status"] != "Active"
                or quantity > product["AvailableQuantity"]):
            failed_items.append(batch_id)
            continue

        result = create_rescue_order(session["user_id"], int(batch_id), quantity)
        if result["status_code"] == 1:
            created_orders.append(result["order_id"])
            cart.pop(batch_id, None)
        else:
            failed_items.append(batch_id)

    session["cart"] = cart
    if created_orders:
        flash(f"Đã tạo {len(created_orders)} đơn hàng thành công.", "success")
    if failed_items:
        flash("Một số sản phẩm hết hàng hoặc tồn kho thay đổi; vui lòng kiểm tra lại giỏ.", "danger")
    if not created_orders and not failed_items:
        flash("Giỏ hàng đang trống.", "warning")
    return redirect(url_for("view_cart"))


if __name__ == "__main__":
  app.run(debug=True, port=5000)