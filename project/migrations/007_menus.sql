create table if not exists menus (
  id integer primary key autoincrement,
  endpoint text unique not null,
  display_name text not null,
  order_no integer default 0,
  admin_only integer default 0
);
