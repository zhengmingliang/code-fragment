package com.alianga.sql;

import com.alibaba.druid.DbType;
import lombok.extern.slf4j.Slf4j;
import net.sf.jsqlparser.JSQLParserException;
import net.sf.jsqlparser.expression.Alias;
import net.sf.jsqlparser.expression.Expression;
import net.sf.jsqlparser.expression.LongValue;
import net.sf.jsqlparser.expression.NullValue;
import net.sf.jsqlparser.expression.operators.relational.ComparisonOperator;
import net.sf.jsqlparser.expression.operators.relational.GreaterThan;
import net.sf.jsqlparser.expression.operators.relational.MinorThanEquals;
import net.sf.jsqlparser.parser.CCJSqlParserUtil;
import net.sf.jsqlparser.schema.Column;
import net.sf.jsqlparser.statement.Statement;
import net.sf.jsqlparser.statement.Statements;
import net.sf.jsqlparser.statement.select.*;
import net.sf.jsqlparser.util.TablesNamesFinder;

import java.util.Collections;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

@Slf4j
public class JSqlUtils {


    /**
     * 拆分 sql 语句（需要用 分号 分隔）
     *
     * @param sqls sql语句
     * @return {@link List }<{@link String }>
     * @throws JSQLParserException jsqlparser解析 sql 异常
     */
    public static List<String> splitSqls(String sqls) throws JSQLParserException {
        Statements statements = CCJSqlParserUtil.parseStatements(sqls);
        List<Statement> statementList = statements.getStatements();
        return statementList.stream().map(Statement::toString).collect(Collectors.toList());
    }

    /**
     * 使用JSqlParser包解析表名，防止druid解析不出来时做补充
     * druid解析oracle语句：select sysdate from dual，无法解析dual
     *
     * @param sql sql语句
     * @return 表名
     */
    public static List<String> getTables(String sql) {
        try {
            Statement statement = CCJSqlParserUtil.parse(sql);
            return getTables(statement);
        } catch (JSQLParserException e) {
            log.error("获取表名出现异常", e);
        }
        return Collections.emptyList();
    }
    /**
     * 使用JSqlParser包解析表名，防止druid解析不出来时做补充
     * druid解析oracle语句：select sysdate from dual，无法解析dual
     *
     * @param statement sql语句
     * @return 表名
     */
    public static List<String> getTables(Statement statement) {
        try {
            if (statement == null) {
                return Collections.emptyList();
            }
            TablesNamesFinder tablesNamesFinder = new TablesNamesFinder();
            return tablesNamesFinder.getTableList(statement);
        } catch (Exception e) {
            log.error("获取表名出现异常", e);
        }
        return Collections.emptyList();
    }

    /**
     * 为SQL添加或修改分页。这是一个总入口。
     *
     * @param sql      原始SQL
     * @param pageNum  页码 (从1开始)
     * @param pageSize 每页大小
     * @param dbType   数据库类型
     * @return 修改后的分页SQL
     * @throws JSQLParserException SQL解析失败
     */
    public static String addOrModifyPagination(String sql, DbType dbType, int pageNum, int pageSize)
            throws JSQLParserException {
        Statement statement = CCJSqlParserUtil.parse(sql);
        if (!(statement instanceof Select)) {
            log.warn("非SELECT语句，将返回原始SQL，sql:{}", sql);
            return sql; // 非SELECT语句直接返回
        }

        Select select = (Select) statement;
        SelectBody selectBody = select.getSelectBody();

        long offset = (long) (pageNum - 1) * pageSize;

        switch (dbType) {
            case mysql:
            case gbase:
            case mariadb:
            case oceanbase:
            case hive:
            case argo:
            case sqlite:
                handleLimit(selectBody, offset, pageSize);
                break;
            case postgresql:
            case gaussdb:
            case oscar:
            case XCloud:
                handleLimitOffset(selectBody, offset, pageSize);
                break;
            case sqlserver:
//            case oracle:
                // Oracle 12c+ and SQL Server 2012+ use the same syntax
                handleSqlServerPagination(selectBody, offset, pageSize);
                break;
            case oracle:
            case dm:
            case oceanbase_oracle:
                // 老版本Oracle和达梦Oracle模式使用ROWNUM
                // 这种方式需要重写整个查询，所以我们返回一个新的Select对象
                select = handleOracleRowNum(select, offset, pageSize);
                break;
//            case GBASE8S:
//                handleSkipFirst(selectBody, offset, pageSize);
//                break;
            default:
                throw new UnsupportedOperationException("Unsupported database type: " + dbType);
        }

        return select.toString();
    }

    /**
     * 获取 sql 中分页大小，如果没有分页或者获取失败，则返回 -1，如果查询语句中包含临时表或不包含表名时，则返回 -2
     *
     * @param sql      原始SQL
     * @param dbType   数据库类型
     * @return 修改后的分页SQL
     * @throws JSQLParserException SQL解析失败
     */
    public static long getLimitByJSqlParser(String sql, DbType dbType) throws JSQLParserException {
        Statement statement = CCJSqlParserUtil.parse(sql);
        if (!(statement instanceof Select)) {
            log.warn("非SELECT语句，将返回原始SQL，sql:{}", sql);
            return -1; // 非SELECT语句直接返回
        }

        Select select = (Select) statement;
        List<String> tables = getTables(select);
        // 如果是临时表，则返回 -2
        if (isTempTable(tables)) {
            return -2;
        }
        SelectBody selectBody = select.getSelectBody();

        switch (dbType) {
            case mysql:
            case gbase:
            case mariadb:
            case oceanbase:
            case hive:
            case argo:
            case sqlite:
            case postgresql:
            case gaussdb:
            case oscar:
            case XCloud:
                return getLimit(selectBody);
            case sqlserver:
//            case oracle:
                // Oracle 12c+ and SQL Server 2012+ use the same syntax
                return getSqlServerPagination(selectBody);
            case oracle:
            case dm:
            case oceanbase_oracle:
                // 老版本Oracle和达梦Oracle模式使用ROWNUM
                // 这种方式需要重写整个查询，所以我们返回一个新的Select对象
                // todo
                return getOraclePagination(selectBody);
//            case GBASE8S:
//                handleSkipFirst(selectBody, offset, pageSize);
//                break;
            default:
                throw new UnsupportedOperationException("Unsupported database type: " + dbType);
        }
    }

    private static long getLimit(SelectBody selectBody) {
        if (selectBody instanceof PlainSelect) {
            PlainSelect plainSelect = (PlainSelect) selectBody;

            Limit limit = plainSelect.getLimit();
            return getLimitFromLimit(limit);
        } else if (selectBody instanceof SetOperationList) {
            SetOperationList setOpList = (SetOperationList) selectBody;
            Limit limit = setOpList.getLimit();
            return getLimitFromLimit(limit);
        } else {
            log.warn("不支持的SELECT语句类型，将返回原始SQL");
        }
        return -1;
    }

    private static long getLimitFromLimit(Limit limit) {
        if (limit == null) {
            return -1;
        }

        Expression rowCount = limit.getRowCount();
        if (rowCount == null) {
            return -1;
        }
        if (rowCount instanceof LongValue) {
            return ((LongValue) rowCount).getValue();
        }
        // 其他占位符等情况，则返回 -1
        return -1;
    }

    // 处理器1: LIMIT ...  ...
    private static void handleLimit(SelectBody selectBody, long offset, long pageSize) {
        if (selectBody instanceof PlainSelect) {
            PlainSelect plainSelect = (PlainSelect) selectBody;
            Limit limit = plainSelect.getLimit();
            if (limit == null) {
                limit = new Limit();
                plainSelect.setLimit(limit);
            }
            limit.setRowCount(new LongValue(pageSize));
            limit.setOffset(new LongValue(offset));
        } else if (selectBody instanceof SetOperationList) {
            SetOperationList setOpList = (SetOperationList) selectBody;
            Limit limit = setOpList.getLimit();
            if (limit == null) {
                limit = new Limit();
                setOpList.setLimit(limit);
            }
            limit.setRowCount(new LongValue(pageSize));
            limit.setOffset(new LongValue(offset));
        }
    }

    // 处理器2: LIMIT ... OFFSET ...
    private static void handleLimitOffset(SelectBody selectBody, long offset, long pageSize) {
        if (selectBody instanceof PlainSelect) {
            PlainSelect plainSelect = (PlainSelect) selectBody;
            Limit limit = plainSelect.getLimit();
            if (limit == null) {
                limit = new Limit();
                plainSelect.setLimit(limit);
            }
            limit.setRowCount(new LongValue(pageSize));
            Offset offsetObject = plainSelect.getOffset();
            if (offsetObject == null) {
                offsetObject = new Offset();
                plainSelect.setOffset(offsetObject);
            }
            setOffsetValue(offset, offsetObject);
        } else if (selectBody instanceof SetOperationList) {
            SetOperationList setOpList = (SetOperationList) selectBody;
            Limit limit = setOpList.getLimit();
            if (limit == null) {
                limit = new Limit();
                setOpList.setLimit(limit);
            }
            limit.setRowCount(new LongValue(pageSize));
            Offset offsetObject = setOpList.getOffset();
            if (offsetObject == null) {
                offsetObject = new Offset();
                setOpList.setOffset(offsetObject);
            }
            setOffsetValue(offset, offsetObject);
        }
    }

    // 处理器2: OFFSET ... FETCH ...
    private static void handleFetchOffset(SelectBody selectBody, long offset, long pageSize) {
        if (selectBody instanceof PlainSelect) {
            PlainSelect plainSelect = (PlainSelect) selectBody;
            // JSqlParser支持在PlainSelect和SetOperationList上直接设置
            Offset offsetObj = plainSelect.getOffset();
            if (offsetObj == null) {
                offsetObj = new Offset();
                plainSelect.setOffset(offsetObj);
            }
            offsetObj.setOffsetParam("ROWS");
            setOffsetValue(offset, offsetObj);

            Fetch fetch = plainSelect.getFetch();
            if (fetch == null) {
                fetch = new Fetch();
                plainSelect.setFetch(fetch);
            }
            fetch.setFetchParam("ROWS");
            fetch.setRowCount(pageSize);
        } else if (selectBody instanceof SetOperationList) {
            SetOperationList setOpList = (SetOperationList) selectBody;
            // JSqlParser支持在PlainSelect和SetOperationList上直接设置
            Offset offsetObj = setOpList.getOffset();
            if (offsetObj == null) {
                offsetObj = new Offset();
                offsetObj.setOffsetParam("ROWS");
                setOpList.setOffset(offsetObj);
            }
            setOffsetValue(offset, offsetObj);

            Fetch fetch = setOpList.getFetch();
            if (fetch == null) {
                fetch = new Fetch();
                setOpList.setFetch(fetch);
            }
            fetch.setFetchParam("ROWS");
            fetch.setRowCount(pageSize);
//            JdbcParameter jdbcParameter = new JdbcParameter();
//            jdbcParameter.setUseFixedIndex(false);
//            fetch.setFetchJdbcParameter(jdbcParameter); // 使用 "ROWS" 而不是 "?"
        }

    }

    /**
     * 设置偏移值 , 对 JSqlParser 不同版本的适配
     *
     * @param offset       抵消
     * @param offsetObject 补偿对象
     */
    public static void setOffsetValue(long offset, Offset offsetObject) {
        // 4.0 版本
//        offsetObject.setOffset(offset);
        // 4.6 版本
        offsetObject.setOffset(new LongValue(offset));
    }

    // 处理器2: OFFSET ... FETCH ...
    private static void handleSqlServerPagination(SelectBody selectBody, long offset, long pageSize) {
        if (selectBody instanceof PlainSelect) {
            PlainSelect plainSelect = (PlainSelect) selectBody;
            if (offset == 0) {
                Top top = plainSelect.getTop();
                if (top == null) {
                    top = new Top();
                    plainSelect.setTop(top);
                }
                top.setExpression(new LongValue(pageSize));
                return;
            }
            Top top = plainSelect.getTop();
            if (top != null) {
                plainSelect.setTop(null);
            }

            if (plainSelect.getOrderByElements() == null || plainSelect.getOrderByElements().isEmpty()) {
                OrderByElement orderByElement = getOrderByNullElement();
                plainSelect.setOrderByElements(Collections.singletonList(orderByElement));
                log.warn("SQL Server 分页查询未添加ORDER BY子句，已添加'ORDER BY (SELECT NULL)'");
            }
        } else if (selectBody instanceof SetOperationList) {
            SetOperationList setOpList = (SetOperationList) selectBody;
            if (setOpList.getOrderByElements() == null || setOpList.getOrderByElements().isEmpty()) {
                OrderByElement orderByElement = getOrderByNullElement();
                setOpList.setOrderByElements(Collections.singletonList(orderByElement));
                log.warn("SQL Server 分页查询未添加ORDER BY子句，已添加'ORDER BY (SELECT NULL)'");
            }
        }
        handleFetchOffset(selectBody, offset, pageSize);

    }

    /**
     * 获取 null元素排序 sql
     *
     * @return {@link OrderByElement }
     */
    private static OrderByElement getOrderByNullElement() {
        OrderByElement orderByElement = new OrderByElement();
        SubSelect subSelect = new SubSelect();
        PlainSelect select = new PlainSelect();
        select.addSelectItems(new SelectExpressionItem(new NullValue()));
        subSelect.setSelectBody(select);
        orderByElement.setExpression(subSelect);
        return orderByElement;
    }

    private static long getSqlServerPagination(SelectBody selectBody) {
        if (selectBody instanceof PlainSelect) {
            PlainSelect plainSelect = (PlainSelect) selectBody;
            Top top = plainSelect.getTop();
            if (top != null) {
                Expression expression = top.getExpression();
                if (expression instanceof LongValue) {
                    return ((LongValue) expression).getValue();
                }
                log.warn("不支持TOP表达式:{}", expression);
                return -1;
            }
            Fetch fetch = plainSelect.getFetch();
            if (fetch != null) {
                return fetch.getRowCount();
            }
        } else if (selectBody instanceof SetOperationList) {
            SetOperationList setOpList = (SetOperationList) selectBody;
            Fetch fetch = setOpList.getFetch();
            if (fetch != null) {
                return fetch.getRowCount();
            }
        }

        return -1;
    }

    /**
     * 获取oracle分页大小
     *
     * @param selectBody 选择身体
     * @return long
     */
    private static long getOraclePagination(SelectBody selectBody) {
        if (selectBody instanceof PlainSelect) {
            PlainSelect plainSelect = (PlainSelect) selectBody;

            Fetch fetch = plainSelect.getFetch();
            if (fetch != null) {
                return fetch.getRowCount();
            }

            // 主要用来兼容达梦数据库的 limit 语法
            Limit limit = plainSelect.getLimit();
            if (limit != null) {
                Expression rowCount = limit.getRowCount();
                if (rowCount instanceof LongValue) {
                    return ((LongValue) rowCount).getValue();
                }
            }
        } else if (selectBody instanceof SetOperationList) {
            SetOperationList setOpList = (SetOperationList) selectBody;
            Fetch fetch = setOpList.getFetch();
            if (fetch != null) {
                return fetch.getRowCount();
            }
        }

        Optional<Pager> optional = parseRowNum(selectBody);
        if (optional.isPresent()) {
            return optional.get().getPageSize();
        }
        return -1;
    }

    /**
     * 解析传统的 ROWNUM 嵌套子查询语法
     * 识别模式: SELECT * FROM (SELECT ..., ROWNUM rnum FROM (...) WHERE ROWNUM <= end) WHERE rnum > start
     */
    private static Optional<Pager> parseRowNum(SelectBody selectBody) {
        // ROWNUM 分页模式一定是一个 PlainSelect
        if (!(selectBody instanceof PlainSelect)) {
            return Optional.empty();
        }
        PlainSelect outerSelect = (PlainSelect) selectBody;

        // 1. 检查外部查询结构：FROM子句必须是子查询，且有WHERE条件
        if (!(outerSelect.getFromItem() instanceof SubSelect) || outerSelect.getWhere() == null) {
            return Optional.empty();
        }

        // 2. 解析外部WHERE条件，获取 offset (e.g., WHERE rnum > 20)
        long offset = -1;
        String rowNumAlias;

        if (outerSelect.getWhere() instanceof ComparisonOperator) {
            ComparisonOperator where = (ComparisonOperator) outerSelect.getWhere();
            // 支持 "rnum > 20" 或 "rnum >= 21"
            if (where.getLeftExpression() instanceof Column && where.getRightExpression() instanceof LongValue) {
                rowNumAlias = ((Column) where.getLeftExpression()).getColumnName();
                long value = ((LongValue) where.getRightExpression()).getValue();

                String op = where.getStringExpression();
                if (">".equals(op)) {
                    offset = value;
                } else if (">=".equals(op)) {
                    offset = value - 1;
                }
            } else {
                rowNumAlias = null;
            }
        } else {
            rowNumAlias = null;
        }
        if (offset == -1 || rowNumAlias == null) {
            return Optional.empty();
        }

        // 3. 进入中间层子查询
        SubSelect middleSubSelect = (SubSelect) outerSelect.getFromItem();
        if (!(middleSubSelect.getSelectBody() instanceof PlainSelect)) {
            return Optional.empty();
        }
        PlainSelect middleSelect = (PlainSelect) middleSubSelect.getSelectBody();

        // 4. 检查中间层查询结构：必须有WHERE条件
        if (middleSelect.getWhere() == null) {
            return Optional.empty();
        }

        // 5. 解析中间层WHERE，获取 endRow (e.g., WHERE ROWNUM <= 30)
        long endRow = -1;
        if (middleSelect.getWhere() instanceof ComparisonOperator) {
            ComparisonOperator where = (ComparisonOperator) middleSelect.getWhere();
            // 支持 "ROWNUM <= 30" 或 "ROWNUM < 31"
            if (where.getLeftExpression() instanceof Column &&
                    "ROWNUM".equalsIgnoreCase(((Column) where.getLeftExpression()).getColumnName())
                    && where.getRightExpression() instanceof LongValue) {
                long value = ((LongValue) where.getRightExpression()).getValue();
                String op = where.getStringExpression();
                if ("<=".equals(op)) {
                    endRow = value;
                } else if ("<".equals(op)) {
                    endRow = value - 1;
                }
            }
        }
        if (endRow == -1) {
            return Optional.empty();
        }

        // 6. 验证 ROWNUM 别名在中间层 SELECT 列表中
        boolean aliasFound = middleSelect.getSelectItems().stream()
                .filter(item -> item instanceof SelectExpressionItem)
                .map(item -> (SelectExpressionItem) item)
                .anyMatch(item -> item.getAlias() != null
                        && rowNumAlias.equalsIgnoreCase(item.getAlias().getName())
                        && item.getExpression() instanceof Column
                        && "ROWNUM".equalsIgnoreCase(((Column) item.getExpression()).getColumnName()));

        if (!aliasFound) {
            return Optional.empty();
        }

        // 7. 计算 pageSize 并返回
        long pageSize = endRow - offset;
        if (pageSize > 0) {
            int pageNo = pageSize <= 0 ? 1 : (int) (offset / pageSize + 1);
            return Optional.of(Pager.of(pageNo, (int) pageSize));
        }

        return Optional.empty();
    }

    // 处理器3: SKIP ... FIRST ...
    private static void handleSkipFirst(SelectBody selectBody, long offset, long pageSize) {
        if (selectBody instanceof PlainSelect) {
            PlainSelect plainSelect = (PlainSelect) selectBody;

            Skip skip = plainSelect.getSkip();
            if (skip == null) {
                skip = new Skip();
                plainSelect.setSkip(skip);
            }
            skip.setRowCount(offset);

            First first = plainSelect.getFirst();
            if (first == null) {
                first = new First();
                plainSelect.setFirst(first);
            }
            first.setRowCount(pageSize);
        }
        // 注意：UNION查询与SKIP/FIRST的组合在某些数据库中语法可能有限制，
        // 这里只处理最常见的PlainSelect场景。
    }

    // 处理器4: Oracle ROWNUM (最复杂)
    private static Select handleOracleRowNum(Select originalSelect, long offset, long pageSize) {
        long endRow = offset + pageSize;

        // 确保原始查询有ORDER BY，否则ROWNUM分页是无意义的
        SelectBody selectBody = originalSelect.getSelectBody();
        if (selectBody instanceof PlainSelect) {
            if (((PlainSelect) selectBody).getOrderByElements() == null) {
                log.warn("ROWNUM pagination without ORDER BY is not recommended.");
            }
        }

        // 外部查询: SELECT * FROM ( ... ) WHERE rnum >= ?
        PlainSelect outerSelect = new PlainSelect();
        outerSelect.addSelectItems(new AllColumns()); // SELECT *

        // 中间查询: SELECT t.*, ROWNUM AS rnum FROM ( original_sql ) t WHERE ROWNUM <= ?
        PlainSelect middleSelect = new PlainSelect();
        // SELECT t.*, ROWNUM as rnum
        middleSelect.addSelectItems(new SelectExpressionItem(new Column("t.*")));
        middleSelect.addSelectItems(new SelectExpressionItem(new Column("ROWNUM")).withAlias(new Alias("rnum")));

        // FROM ( original_sql ) t
        SubSelect originalSubSelect = new SubSelect();
        originalSubSelect.setSelectBody(selectBody);
        originalSubSelect.setAlias(new Alias("t"));
        middleSelect.setFromItem(originalSubSelect);

        // WHERE ROWNUM <= endRow
        middleSelect.setWhere(new MinorThanEquals().withLeftExpression(new Column("ROWNUM"))
                .withRightExpression(new LongValue(endRow)));

        // 将中间查询包装成子查询，用于外部查询
        SubSelect middleSubSelect = new SubSelect();
        middleSubSelect.setSelectBody(middleSelect);
        middleSubSelect.setAlias(new Alias("")); // Oracle子查询可以没有别名
        outerSelect.setFromItem(middleSubSelect);

        // WHERE rnum >= startRow
        outerSelect.setWhere(new GreaterThan().withLeftExpression(new Column("rnum"))
                .withRightExpression(new LongValue(offset)));

        // 创建一个新的Select对象并返回
        Select newSelect = new Select();
        newSelect.setSelectBody(outerSelect);
        return newSelect;
    }

    /**
     * 是否是临时表
     *
     * @param tables 表
     * @return boolean
     */
    private static boolean isTempTable(List<String> tables) {
        if (tables.isEmpty() || (tables.size() == 1 && "dual".equalsIgnoreCase(tables.get(0)))) {
            return true;
        }
        return false;
    }

}
