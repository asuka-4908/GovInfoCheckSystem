create table if not exists users (
  id integer primary key autoincrement,
  name text not null
);

insert into users(name) values ('Alice');
insert into users(name) values ('Bob');

