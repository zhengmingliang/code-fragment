# SQL工具与分页工具库

这是一个基于JSqlParser的SQL工具库，提供了SQL解析、分页处理和表名提取等功能。支持多种数据库类型的分页查询。

## 功能特性

### JSqlUtils 主要功能

- **SQL语句拆分**: 将多个SQL语句按分号分割成单独的语句
- **表名解析**: 从SQL语句中提取使用的表名
- **分页处理**: 为SQL添加分页功能，支持多种数据库
- **分页信息获取**: 从SQL中解析分页大小信息

### Pager 分页类特性

- **泛型支持**: 支持任何类型的数据分页
- **灵活配置**: 可配置页面大小、最大页面大小等参数
- **自动计算**: 自动计算开始行、总页数等分页信息
- **安全防护**: 支持限制最大页面大小，防止资源滥用

## 支持的数据库类型

### 使用 LIMIT ... OFFSET 语法的数据库

- MySQL
- GBase
- MariaDB
- OceanBase
- Hive
- Argo
- SQLite

### 使用 LIMIT ... OFFSET 语法的数据库

- PostgreSQL
- GaussDB
- Oscar
- XCloud

### 使用 OFFSET ... FETCH 语法的数据库

- SQL Server 2012+
- Oracle 12c+

### 使用 ROWNUM 语法的数据库

- Oracle (老版本)
- 达梦数据库
- OceanBase Oracle模式

## 依赖要求

```xml
<!-- JSqlParser - SQL解析库 -->
<dependency>
    <groupId>net.sf.jsqlparser</groupId>
    <artifactId>jsqlparser</artifactId>
    <version>4.6+</version>
</dependency>

<!-- Druid - 数据库连接池 -->
<dependency>
    <groupId>com.alibaba</groupId>
    <artifactId>druid</artifactId>
    <version>1.2.16+</version>
</dependency>

<!-- Lombok - 日志支持 -->
<dependency>
    <groupId>org.projectlombok</groupId>
    <artifactId>lombok</artifactId>
    <version>1.18.24+</version>
    <scope>provided</scope>
</dependency>
```

## 使用示例

### 1. 添加分页到SQL语句

```java
import com.alianga.sql.JSqlUtils;
import com.alibaba.druid.DbType;

// MySQL分页
String originalSql = "SELECT * FROM user WHERE status = 1";
String pagedSql = JSqlUtils.addOrModifyPagination(
    originalSql, 
    DbType.mysql, 
    2,  // 页码
    10  // 每页大小
);
System.out.println(pagedSql);
// 输出: SELECT * FROM user WHERE status = 1 LIMIT 10 OFFSET 10

// PostgreSQL分页
String pagedSqlPg = JSqlUtils.addOrModifyPagination(
    originalSql, 
    DbType.postgresql, 
    3, 
    20
);
System.out.println(pagedSqlPg);
// 输出: SELECT * FROM user WHERE status = 1 LIMIT 20 OFFSET 40

// Oracle分页 (使用ROWNUM)
String pagedSqlOracle = JSqlUtils.addOrModifyPagination(
    originalSql, 
    DbType.oracle, 
    1, 
    5
);
System.out.println(pagedSqlOracle);
// 输出: SELECT * FROM (SELECT t.*, ROWNUM AS rnum FROM (SELECT * FROM user WHERE status = 1) t WHERE ROWNUM <= 5) WHERE rnum >= 0
```

### 2. 拆分SQL语句

```java
String multipleSqls = "SELECT * FROM user; INSERT INTO log VALUES (1); SELECT COUNT(*) FROM user;";
List<String> sqlList = JSqlUtils.splitSqls(multipleSqls);
for (String sql : sqlList) {
    System.out.println(sql);
}
// 输出:
// SELECT * FROM user
// INSERT INTO log VALUES (1)
// SELECT COUNT(*) FROM user
```

### 3. 提取表名

```java
String sql = "SELECT u.name, p.title FROM user u JOIN post p ON u.id = p.user_id";
List<String> tables = JSqlUtils.getTables(sql);
System.out.println(tables); // 输出: [user, post]
```

### 4. 获取分页大小

```java
String pagedSql = "SELECT * FROM user LIMIT 10 OFFSET 20";
long pageSize = JSqlUtils.getLimitByJSqlParser(pagedSql, DbType.mysql);
System.out.println(pageSize); // 输出: 10
```

### 5. 使用分页类

```java
import com.alianga.sql.Pager;

// 创建分页对象
Pager<User> pager = new Pager<>(1, 10); // 第1页，每页10条

// 设置总记录数
pager.setTotalCount(156);

// 获取开始行
int startRow = pager.getStartRow(); // 返回 0

// 获取分页后的数据（实际使用时需要从数据库获取）
List<User> pageContent = userService.getUserList(startRow, pager.getPageSize());
pager.setPageContent(pageContent);

// 获取分页信息
int pageNo = pager.getPageNo();           // 1
int pageSize = pager.getPageSize();       // 10
long totalPage = pager.getTotalPage();    // 16
long totalCount = pager.getTotalCount();  // 156

// 使用静态工厂方法
Pager<User> pager2 = Pager.of(2, 20); // 第2页，每页20条
```

## 注意事项

### Oracle分页注意事项

- Oracle分页需要ORDER BY子句，否则ROWNUM分页可能产生意外结果
- 如果原始SQL没有ORDER BY，会输出警告日志

### SQL Server分页注意事项

- SQL Server分页查询必须包含ORDER BY子句
- 如果缺少ORDER BY，会自动添加 `ORDER BY (SELECT NULL)`

### 临时表处理

- 包含临时表（如Oracle的`dual`表）的SQL查询在获取分页大小时会返回-2
- 这类查询通常不需要分页处理

### 性能建议

- 对于大量数据的分页查询，建议使用基于游标的分页（如keyset pagination）替代传统的OFFSET分页
- 合理设置页面大小，避免一次性查询过多数据


## 更新日志

### v1.0.0

- 初始版本发布
- 支持多种数据库分页
- 提供SQL解析和表名提取功能
